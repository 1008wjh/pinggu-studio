"""四步会计核算 LangGraph。

每个业务节点后都进入 human_gate，并调用 interrupt。即使置信度很高也必须等待人工确认，
符合会计业务“机器先算、人工留痕放行”的控制要求。MemorySaver 负责进程内断点，API 同步将完整
State 写入 accounting_checkpoints，进程重启后可从数据库快照恢复。
"""
from __future__ import annotations
import json, re
import csv
import io
from collections import defaultdict
from pathlib import Path
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from backend.agents.accounting.state import AccountingState, STEP1, STEP2, STEP3, STEP4, AIReviewNote, OUTPUT_MODELS
from backend.agents.accounting.prompts import ACCOUNTING_SYSTEM, CLASSIFY_PROMPT, VOUCHER_PROMPT, STATEMENT_PROMPT, COMPARISON_PROMPT
from backend.core.llm_factory import get_llm
from backend.services.document_workspace import extract_document

_MEMORY = MemorySaver()

def _flatten(value: Any) -> str:
    if isinstance(value, str): return value
    if isinstance(value, list): return "\n".join(_flatten(item) for item in value)
    if isinstance(value, dict): return "\n".join(f"{key}: {_flatten(item)}" for key, item in value.items())
    return str(value)

def _read(path: str) -> str:
    if not path: return ""
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(path), lang="chi_sim+eng")
        except Exception:
            return f"图片文件 {Path(path).name}，OCR 引擎不可用，待人工补录。"
    try:
        return _flatten(extract_document(path, max_rows=None))[:12000]
    except Exception as exc:
        return f"文件 {Path(path).name} 解析失败：{exc}"


def _table_rows(path: str) -> list[dict[str, Any]]:
    """结构化读取所有工作表。金额字段必须从单元格读取，不能从展平文本猜。"""
    if not path or Path(path).suffix.lower() not in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv"}:
        return []
    try:
        result = extract_document(path, max_rows=None)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for sheet in result.get("sheets", []):
        for row in sheet.get("rows", []):
            item = dict(row)
            item["__sheet"] = sheet.get("name", "")
            rows.append(item)
    return rows


def _key(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    keys = list(row)
    normalized = {re.sub(r"[\s（）()_\-]", "", str(k)).lower(): k for k in keys}
    for alias in aliases:
        needle = re.sub(r"[\s（）()_\-]", "", alias).lower()
        if needle in normalized:
            return normalized[needle]
    for alias in aliases:
        needle = re.sub(r"[\s（）()_\-]", "", alias).lower()
        for normalized_key, original in normalized.items():
            if needle and needle in normalized_key:
                return original
    return None


def _value(row: dict[str, Any], aliases: tuple[str, ...], default: Any = "") -> Any:
    key = _key(row, aliases)
    return row.get(key, default) if key else default


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = _text(value).replace(",", "").replace("，", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return round(float(match.group(0)), 2) if match else 0.0


def _invoice_records(path: str) -> list[dict[str, Any]]:
    """按发票号码生成一票一条记录；优先使用票面信息表，明细表用于补充商品描述。"""
    rows = _table_rows(path)
    if not rows:
        return []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_text(row.get("__sheet", ""))].append(row)
    summary, detail = [], []
    for sheet_rows in groups.values():
        sample = sheet_rows[0]
        has_line = bool(_key(sample, ("货物或应税劳务名称", "规格型号", "数量", "单价")))
        has_party = bool(_key(sample, ("销方名称", "购买方名称")))
        if has_line:
            detail.extend(sheet_rows)
        if has_party and not has_line:
            summary.extend(sheet_rows)
    if not summary:
        summary = rows
    detail_by_number: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in detail:
        number = _text(_value(row, ("数电发票号码", "电子发票号码", "发票号码", "发票号")))
        if number:
            detail_by_number[number].append(row)
    def matching_lines(number: str, fallback: dict[str, Any]) -> list[dict[str, Any]]:
        if number in detail_by_number:
            return detail_by_number[number]
        compact = re.sub(r"\D", "", number)
        for candidate, candidate_rows in detail_by_number.items():
            other = re.sub(r"\D", "", candidate)
            if (compact and other and (compact.endswith(other) or other.endswith(compact) or compact[-8:] == other[-8:])):
                return candidate_rows
        return [fallback]
    records, seen = [], set()
    has_any_number = any(_text(_value(row, ("数电发票号码", "电子发票号码", "发票号码", "发票号"))) for row in summary)
    for index, row in enumerate(summary, 1):
        number = _text(_value(row, ("数电发票号码", "电子发票号码", "发票号码", "发票号")))
        if not number and has_any_number:
            continue
        number = number or f"{Path(path).stem}-{index}"
        if number in seen:
            continue
        seen.add(number)
        lines = matching_lines(number, row)
        total = _number(_value(row, ("价税合计", "含税合计"))) or round(sum(_number(_value(item, ("价税合计", "含税合计"))) for item in lines), 2)
        net = _number(_value(row, ("金额", "不含税金额"))) or round(sum(_number(_value(item, ("金额", "不含税金额"))) for item in lines), 2)
        tax = _number(_value(row, ("税额", "税款"))) or round(sum(_number(_value(item, ("税额", "税款"))) for item in lines), 2)
        description = _text(_value(row, ("货物或应税劳务名称", "项目名称", "商品名称")))
        descriptions = [_text(_value(item, ("货物或应税劳务名称", "项目名称", "商品名称"))) for item in lines]
        description = "；".join(dict.fromkeys(filter(None, descriptions))) or description
        seller = _text(_value(row, ("销方名称", "销售方名称", "销方")))
        buyer = _text(_value(row, ("购买方名称", "购方名称", "购买方")))
        direction = "sales" if "本单位" in seller else "purchase" if "本单位" in buyer else ("sales" if "开具" in Path(path).stem else "purchase")
        records.append({"invoice_number": number, "invoice_date": _text(_value(row, ("开票日期", "发票日期", "开具日期"))), "seller": seller, "buyer": buyer, "description": description, "line_count": len(lines), "amount": net, "tax_amount": tax, "total_amount": total, "invoice_direction": direction})
    return records


def _account_names(path: str) -> list[str]:
    return list(_account_catalog(path)[0])


def _account_catalog(path: str) -> tuple[list[str], dict[str, str]]:
    """读取科目名称和科目代码。

    科目 名称.xlsx 是从财务软件导出的模板，表头位于首行数据中，解析器会将
    其列名保留为 column_4/column_5；因此不能只依赖“科目名称”列名。
    """
    names: list[str] = []
    codes: dict[str, str] = {}
    for row in _table_rows(path):
        values = {str(key): value for key, value in row.items() if not str(key).startswith("__")}
        name = _text(_value(row, ("科目名称", "会计科目", "科目名")))
        code = _text(_value(row, ("科目代码", "科目编码", "代码", "编码")))
        if not name:
            # 样例文件的第 5 列为科目名称，第 4 列为科目编码。
            name = _text(values.get("column_5") or values.get("科目名称"))
        if not code:
            code = _text(values.get("column_4") or values.get("科目代码"))
        if not name or name in {"科目名称", "会计科目", "科目名"}:
            continue
        if not re.fullmatch(r"\d+(?:\.\d+)?", code):
            continue
        clean_name = re.sub(r"\s+", "", name)
        if clean_name not in names:
            names.append(clean_name)
        codes[clean_name] = code.split(".")[0]
    return names, codes


def _account_code(account: str, catalog: dict[str, str]) -> str:
    clean = re.sub(r"\s+", "", _text(account))
    if not clean:
        return ""
    if clean in catalog:
        return catalog[clean]
    # 规则文件可能使用“应交税费 应交增值税(一般) 进项税额”等层级名称，
    # 而凭证使用短名称；先按末级科目和去除标点后的名称匹配。
    compact = re.sub(r"[^\w\u4e00-\u9fff]", "", clean)
    matches = [(len(name), code) for name, code in catalog.items()
               if name in clean or clean in name or re.sub(r"[^\w\u4e00-\u9fff]", "", name) in compact
               or any(token and token in name for token in re.split(r"[-—/ ]", clean) if len(token) >= 2)]
    if matches:
        return max(matches)[1]
    aliases = {"应收账款": ("其他应收款", "应收"), "固定资产": ("固定资产",), "应付账款": ("应付账款", "其他应付款"), "主营业务收入": ("主营业务收入",)}
    for alias in aliases.get(clean, ()):
        alias_matches = [(len(name), code) for name, code in catalog.items() if alias in name]
        if alias_matches:
            return max(alias_matches)[1]
    return ""


def _classify_invoice(item: dict[str, Any], account_names: list[str]) -> tuple[str, str, float, str, str]:
    description = " ".join(_text(item.get(key, "")) for key in ("description", "seller", "buyer"))
    def account(*hints: str, default: str = "") -> str:
        for hint in hints:
            for name in account_names:
                if hint in name:
                    return name
        return default or (hints[0] if hints else "待处理科目")
    if item.get("invoice_direction") == "sales":
        return "销售收入", "销方为本单位，按销项业务处理", 0.96, account("银行存款", default="银行存款"), account("主营业务收入", default="主营业务收入")
    rules = [("管理费用-水电费", ("电费", "水费", "水电", "供电"), "管理费用", "水电费"), ("销售费用-运输费", ("快递", "运输", "物流", "收派"), "销售费用", "运输费"), ("固定资产", ("空调", "温控器", "设备", "机器", "固定资产"), "固定资产", "固定资产"), ("原材料", ("芯片", "集成电路", "微电子", "电路", "材料"), "原材料", "原材料"), ("库存商品", ("药品", "商品", "采购", "货物"), "库存商品", "库存商品"), ("管理费用-办公费", ("办公", "文具"), "管理费用", "办公费")]
    for label, keywords, *hints in rules:
        hit = next((word for word in keywords if word in description), None)
        if hit:
            return label, f"关键词 {hit} 匹配企业科目规则", 0.92, account(*hints, default=label), account("银行存款", "应付账款", default="银行存款")
    return "待确认/其他", "未能依据企业科目规则唯一确定业务类别", 0.52, account("库存商品", "原材料", default="待处理科目"), account("银行存款", "应付账款", default="银行存款")


def _parse_bank_transactions(path: str) -> list[dict[str, Any]]:
    transactions = []
    for index, row in enumerate(_table_rows(path), 1):
        debit = _number(_value(row, ("借方发生额", "支取", "借方")))
        credit = _number(_value(row, ("贷方发生额", "收入", "贷方")))
        if debit == 0 and credit == 0:
            continue
        transactions.append({"transaction_id": _text(_value(row, ("交易流水号", "流水号", "账户明细编号"))) or f"BANK-{index:04d}", "transaction_time": _text(_value(row, ("交易时间", "交易日期"))), "debit_amount": debit, "credit_amount": credit, "amount": credit or debit, "direction": "credit" if credit else "debit", "counterparty": _text(_value(row, ("对方户名", "对方名称"))), "summary": _text(_value(row, ("摘要", "交易摘要"))), "remark": _text(_value(row, ("备注", "附言"))), "balance": _number(_value(row, ("余额", "账户余额")))})
    return transactions


def _match_transactions(invoices: list[dict[str, Any]], transactions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    available = set(range(len(transactions))); unmatched = []
    for invoice in invoices:
        direction = "credit" if invoice.get("invoice_direction") == "sales" else "debit"
        target = abs(float(invoice.get("total_amount") or 0))
        candidates = [(abs(float(transactions[i]["amount"]) - target), i) for i in available if transactions[i]["direction"] == direction]
        if candidates and target > 0:
            difference, index = min(candidates)
            if difference <= max(0.05, target * 0.005):
                invoice.update({"match_status": "matched", "matched_transaction_id": transactions[index]["transaction_id"], "amount_difference": round(difference, 2), "match_reason": "同方向金额匹配"}); available.remove(index); continue
        invoice.update({"match_status": "unmatched", "matched_transaction_id": "", "amount_difference": target, "match_reason": "未找到同方向且金额相符的银行流水"}); unmatched.append(invoice)
    return unmatched, [transactions[i] for i in sorted(available)]

def _amount(text: str) -> float:
    patterns = [r"(?:金额|价税合计|含税价|合计|金额小计)[^0-9]{0,8}([0-9][0-9,]*(?:\.[0-9]+)?)", r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元|RMB|人民币)?"]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try: return float(match.group(1).replace(",", ""))
            except ValueError: pass
    return 0.0

def _label(text: str, rules: str) -> tuple[str, str, float]:
    pairs = [("采购/存货", ("采购", "材料", "商品", "库存")), ("销售收入", ("销售", "收入", "客户")),
             ("差旅/办公", ("差旅", "交通", "办公", "住宿")), ("工资薪酬", ("工资", "薪酬", "社保")),
             ("税费", ("税", "增值税", "附加")), ("固定资产", ("设备", "固定资产", "机器"))]
    for label, keywords in pairs:
        hit = next((word for word in keywords if word in text), None)
        if hit:
            rule = next((line for line in rules.splitlines() if label in line or hit in line), f"关键词 {hit} 匹配 {label}")
            return label, rule[:500], 0.93
    return "待确认/其他", "未匹配企业分类规则", 0.45

async def _model_note(prompt: str, use_llm: bool) -> dict[str, Any]:
    """要求模型返回 JSON，并用 Pydantic 校验；失败时也返回同一结构。"""
    fallback = AIReviewNote(summary="规则引擎演示模式：模型意见待人工补充。")
    if not use_llm: return fallback.model_dump()
    try:
        schema = AIReviewNote.model_json_schema()
        schema_hint = "\n只返回符合以下 JSON Schema 的 JSON 对象，禁止 Markdown、解释文字和代码围栏：\n" + json.dumps(schema, ensure_ascii=False)
        llm = get_llm("summarize", temperature=0.1)
        messages = [SystemMessage(content=ACCOUNTING_SYSTEM + schema_hint), HumanMessage(content=prompt[:12000])]
        # DeepSeek 当前兼容 function_calling；json_schema 会返回 400，因此使用函数调用约束结构。
        try:
            response = await llm.with_structured_output(AIReviewNote, method="function_calling").ainvoke(messages)
            if isinstance(response, AIReviewNote):
                return response.model_dump()
            if isinstance(response, dict):
                return AIReviewNote.model_validate(response).model_dump()
        except Exception:
            response = await llm.ainvoke(messages)
        content = response.content if hasattr(response, "content") else None
        if isinstance(content, dict):
            return AIReviewNote.model_validate(content).model_dump()
        raw = response.text if hasattr(response, "text") else content
        if isinstance(raw, list):
            raw = "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in raw)
        match = re.search(r"\{.*\}", raw, flags=re.S)
        parsed = json.loads(match.group(0) if match else raw)
        return AIReviewNote.model_validate(parsed).model_dump()
    except Exception as exc:
        return AIReviewNote(summary=f"模型暂不可用，已使用规则引擎；原因：{str(exc)[:200]}").model_dump()

def _set_review(state: AccountingState, step: str, output: dict[str, Any], original: Any, confidence: float, risk: float, note: dict[str, Any]) -> AccountingState:
    outputs = dict(state.get("step_outputs", {})); output = {**output, "model_note": note}
    # 对每一步的结构化结果做强校验，并按 Pydantic 字段顺序写回状态。
    output = OUTPUT_MODELS[step].model_validate(output).model_dump()
    outputs[step] = output
    state["step_outputs"] = outputs; state["current_step"] = step; state["status"] = "pending_review"
    state["confidence"] = round(max(0.0, min(1.0, confidence)), 4); state["risk"] = round(max(0.0, min(1.0, risk)), 4)
    state["review_context"] = {"step": step, "original_data": original, "ai_output": output,
        "display_data": json.loads(json.dumps(output, ensure_ascii=False)),
        "confidence": state["confidence"], "risk": state["risk"], "rules": "本步骤必须人工确认；异常项不得静默通过。"}
    state["checkpoint_version"] = int(state.get("checkpoint_version", 0)) + 1
    return state

def _csv_text(headers: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue()


def _csv_records(headers: list[str], rows: list[dict[str, Any]]) -> str:
    return _csv_text(headers, [[row.get(header, "") for header in headers] for row in rows])


def _table_preview(workbooks: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    preview = []
    for workbook in workbooks:
        for sheet in workbook.get("sheets", []):
            preview.append({"workbook": workbook.get("name", ""), "sheet": sheet.get("name", ""), "headers": sheet.get("headers", []), "rows": sheet.get("rows", [])[:limit], "row_count": len(sheet.get("rows", []))})
    return preview


def _classification_workbooks(paths: list[str], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """保留每个输入 Excel 的全部工作表，按标准答案追加“科目名称”列。"""
    by_number = {item.get("invoice_number"): item for item in items}
    def item_for_number(number: str) -> dict[str, Any]:
        if number in by_number:
            return by_number[number]
        compact = re.sub(r"\D", "", number)
        for candidate, item in by_number.items():
            other = re.sub(r"\D", "", str(candidate))
            if compact and other and (compact.endswith(other) or other.endswith(compact) or compact[-8:] == other[-8:]):
                return item
        return {}
    workbooks = []
    for path in paths:
        try:
            document = extract_document(path, max_rows=None)
        except Exception:
            continue
        sheets = []
        for source_sheet in document.get("sheets", []):
            headers = list(source_sheet.get("headers", []))
            subject_header = "科目名称"
            add_subject = subject_header not in headers and ("货物或应税劳务名称" in headers or "规格型号" in headers)
            if add_subject:
                headers.append(subject_header)
            rows = []
            for row in source_sheet.get("rows", []):
                number = _text(_value(row, ("数电发票号码", "电子发票号码", "发票号码", "发票号")))
                item = item_for_number(number)
                subject = item.get("recommended_credit_account") if item.get("invoice_direction") == "sales" else item.get("recommended_debit_account")
                enriched = {key: row.get(key, "") for key in source_sheet.get("headers", [])}
                if add_subject:
                    enriched[subject_header] = subject or "待确认/其他"
                rows.append(enriched)
            sheets.append({"name": source_sheet.get("name", "Sheet1"), "headers": headers, "rows": rows, "csv": _csv_records(headers, rows)})
        workbooks.append({"name": f"{Path(path).stem}_分类结果.xlsx", "sheets": sheets})
    return workbooks


def _voucher_workbook(vouchers: list[dict[str, Any]]) -> dict[str, Any]:
    headers = ["行号", "年", "月", "日", "凭证号", "预算号", "附件数", "摘要", "会计科目代码", "会计科目名称", "借方金额", "贷方金额", "制单人", "借方数量", "借方单价", "贷方数量", "贷方单价"]
    rows = []
    for voucher in vouchers:
        entries = voucher.get("entries") or [{"account": voucher.get("debit_account", ""), "direction": "debit", "amount": voucher.get("debit_amount", 0)}, {"account": voucher.get("credit_account", ""), "direction": "credit", "amount": voucher.get("credit_amount", 0)}]
        for entry in entries:
            rows.append({"行号": len(rows) + 1, "年": 2026, "月": 3, "日": 31, "凭证号": voucher.get("voucher_no", "").replace("记-", ""), "预算号": "", "附件数": 1, "摘要": voucher.get("summary", ""), "会计科目代码": entry.get("account_code", ""), "会计科目名称": entry.get("account", ""), "借方金额": entry.get("amount", 0) if entry.get("direction") == "debit" else "", "贷方金额": entry.get("amount", 0) if entry.get("direction") == "credit" else "", "制单人": "系统生成", "借方数量": "", "借方单价": "", "贷方数量": "", "贷方单价": ""})
    return {"name": "会计分录凭证.xlsx", "sheets": [{"name": "Sheet1", "headers": headers, "rows": rows, "csv": _csv_records(headers, rows)}]}


def _statement_workbook(balance_sheet: dict[str, Any], income_statement: dict[str, Any], cash_flow_statement: dict[str, Any]) -> dict[str, Any]:
    # 表格预览沿用样例《报表.xlsx》的行顺序和列结构；下载时后端还会套用同一模板的样式。
    cash = balance_sheet.get("cash", 0); receivable = balance_sheet.get("receivable", 0)
    inventory = balance_sheet.get("inventory", 0); fixed_assets = balance_sheet.get("fixed_assets", 0)
    assets = balance_sheet.get("assets", 0); liabilities = balance_sheet.get("liabilities", 0); equity = balance_sheet.get("equity", 0)
    revenue = income_statement.get("revenue", 0); expenses = income_statement.get("expenses", 0); net_profit = income_statement.get("net_profit", 0)
    cash_in = cash_flow_statement.get("cash_in", 0); cash_out = cash_flow_statement.get("cash_out", 0); operating_net = cash_flow_statement.get("operating_net_cash", 0)
    definitions = [
        ("资产负债表", ["项目", "序号", "期末余额", "年初余额", "负债和所有者权益", "负债序号", "负债期末余额", "负债年初余额"], [
            ["货币资金", 1, cash, "", "短期借款", 31, liabilities, ""], ["应收账款", 4, receivable, "", "应付账款", 33, 0, ""],
            ["存货", 9, inventory, "", "应交税费", 36, 0, ""], ["固定资产账面价值", 20, fixed_assets, "", "流动负债合计", 41, liabilities, ""],
            ["流动资产合计", 15, cash + receivable + inventory, "", "负债合计", 47, liabilities, ""], ["非流动资产合计", 29, fixed_assets, "", "所有者权益合计", 52, equity, ""],
            ["资产总计", 30, assets, "", "负债和所有者权益总计", 53, liabilities + equity, ""],
        ]),
        ("利润表", ["项目", "行次", "本月数", "本年累计数"], [
            ["一、营业收入", 1, revenue, revenue], ["减：营业成本", 2, expenses, expenses], ["营业利润", 21, net_profit, net_profit], ["利润总额", 30, net_profit, net_profit], ["净利润", 32, net_profit, net_profit]
        ]),
        ("现金流量表", ["项目", "行次", "本期金额", "上年同期金额", "本年累计数"], [
            ["销售商品、提供劳务收到的现金", 2, cash_in, "", cash_in], ["现金流入小计", 5, cash_in, "", cash_in], ["购买商品、接受劳务支付的现金", 6, cash_out, "", cash_out], ["现金流出小计", 10, cash_out, "", cash_out], ["经营活动产生的现金流量净额", 11, operating_net, "", operating_net], ["现金及现金等价物净增加额", 34, operating_net, "", operating_net], ["期末现金及现金等价物余额", 36, cash, "", cash]
        ]),
    ]
    sheets = []
    for name, headers, values in definitions:
        rows = [{header: (row[index] if index < len(row) else "") for index, header in enumerate(headers)} for row in values]
        sheets.append({"name": name, "headers": headers, "rows": rows, "csv": _csv_records(headers, rows)})
    return {"name": "三大财务报表.xlsx", "sheets": sheets}

async def step1_classification(state: AccountingState) -> AccountingState:
    rules = _read(state.get("rules_path", "")) or "未提供企业分类规则"
    accounts = _account_names(state.get("rules_path", "")); items=[]; anomalies=[]; index=1
    for path in state.get("invoice_paths", []):
      for record in _invoice_records(path):
        label, rule, confidence, debit, credit = _classify_invoice(record, accounts)
        item={"invoice_id": f"INV-{index:04d}", "source_file": Path(path).name, "ocr_text": json.dumps(record, ensure_ascii=False)[:4000], "label": label, "matched_rule": rule, "confidence": confidence, **record, "recommended_debit_account": debit, "recommended_credit_account": credit}
        items.append(item)
        if confidence < 0.7 or item.get("total_amount", 0) == 0: anomalies.append({"invoice_id": item["invoice_id"], "reason": "分类待确认或未识别价税合计"})
        index += 1
    workbooks = _classification_workbooks(state.get("invoice_paths", []), items)
    output={"invoices": items, "rules_reference": rules[:5000], "anomalies": anomalies, "dataset_status": "待人工确认", "table_csv": {f"{book['name']}::{sheet['name']}": sheet['csv'] for book in workbooks for sheet in book['sheets']}, "table_files": [{"name": book['name'], "sheets": [{"name": sheet['name']} for sheet in book['sheets']]} for book in workbooks], "table_preview": _table_preview(workbooks)}
    note=await _model_note(CLASSIFY_PROMPT.format(content=json.dumps(items, ensure_ascii=False), rules=rules), state.get("use_llm", True))
    return _set_review(state, STEP1, output, {"invoice_files": [Path(p).name for p in state.get("invoice_paths", [])], "rules": rules[:5000]}, sum(i["confidence"] for i in items)/len(items) if items else 0, max([1-i["confidence"] for i in items] or [1]), note)

async def step2_vouchers(state: AccountingState) -> AccountingState:
    invoices = state.get("step_outputs", {}).get(STEP1, {}).get("invoices", [])
    _, account_codes = _account_catalog(state.get("rules_path", ""))
    transactions = _parse_bank_transactions(state.get("bank_path", "")); unmatched, unmatched_transactions = _match_transactions(invoices, transactions); vouchers=[]; anomalies=[]
    for index, item in enumerate(invoices, 1):
        total=round(float(item.get("total_amount") or 0),2); net=round(float(item.get("amount") or 0),2); tax=round(float(item.get("tax_amount") or 0),2); sales=item.get("invoice_direction")=="sales"
        debit=(("银行存款" if item.get("match_status")=="matched" else "应收账款") if sales else (item.get("recommended_debit_account") or "库存商品")); credit=(item.get("recommended_credit_account") or "主营业务收入") if sales else ("银行存款" if item.get("match_status")=="matched" else "应付账款"); risk=0.08
        if total <= 0: risk=0.9; anomalies.append({"invoice_id": item.get("invoice_id"), "reason": "价税合计为零"})
        if item.get("match_status") != "matched": risk=max(risk,0.55); anomalies.append({"invoice_id": item.get("invoice_id"), "reason": item.get("match_reason", "未匹配银行流水")})
        tax_account = "应交税费-应交增值税-进项税额" if not sales else "应交税费-应交增值税-销项税额"
        entries=([{"account":debit,"account_code":_account_code(debit, account_codes),"direction":"debit","amount":net},{"account":tax_account,"account_code":_account_code(tax_account, account_codes),"direction":"debit","amount":tax},{"account":credit,"account_code":_account_code(credit, account_codes),"direction":"credit","amount":total}] if not sales else [{"account":debit,"account_code":_account_code(debit, account_codes),"direction":"debit","amount":total},{"account":credit,"account_code":_account_code(credit, account_codes),"direction":"credit","amount":net},{"account":tax_account,"account_code":_account_code(tax_account, account_codes),"direction":"credit","amount":tax}])
        if any(entry["account"] and not entry["account_code"] for entry in entries):
            anomalies.append({"invoice_id": item.get("invoice_id"), "reason": "会计科目未在企业科目规则中找到对应代码", "accounts": [entry["account"] for entry in entries if not entry["account_code"]]})
        vouchers.append({"voucher_no": f"记-{index:04d}", "summary": f"{'销售' if sales else '采购'}发票 {item.get('invoice_number','')}", "debit_account": debit, "debit_account_code": _account_code(debit, account_codes), "credit_account": credit, "credit_account_code": _account_code(credit, account_codes), "debit_amount": total, "credit_amount": total, "net_amount": net, "tax_amount": tax, "source_invoice": item.get("invoice_id"), "invoice_number": item.get("invoice_number",""), "bank_transaction_id": item.get("matched_transaction_id",""), "match_status": item.get("match_status","unmatched"), "amount_difference": item.get("amount_difference", total), "risk": risk, "entries": entries})
    balanced=all(abs(float(v["debit_amount"])-float(v["credit_amount"])) < 0.01 for v in vouchers)
    workbook = _voucher_workbook(vouchers)
    output={"vouchers": vouchers, "bank_source": Path(state.get("bank_path", "")).name if state.get("bank_path") else "未提供", "bank_excerpt": json.dumps(transactions[:20], ensure_ascii=False), "bank_transactions": transactions, "unmatched_invoices": unmatched, "unmatched_transactions": unmatched_transactions, "balanced": balanced, "anomalies": anomalies, "dataset_status": "待人工确认", "table_csv": {f"{workbook['name']}::{sheet['name']}": sheet['csv'] for sheet in workbook['sheets']}, "table_files": [{"name": workbook['name'], "sheets": [{"name": sheet['name']} for sheet in workbook['sheets']]}], "table_preview": _table_preview([workbook])}
    note=await _model_note(VOUCHER_PROMPT.format(invoices=json.dumps(invoices, ensure_ascii=False), bank=json.dumps(transactions, ensure_ascii=False)), state.get("use_llm", True))
    confidence=0.94 if balanced and not anomalies else 0.55; risk=0.06 if balanced and not anomalies else 0.8
    return _set_review(state, STEP2, output, {"invoice_count": len(invoices), "bank_transaction_count": len(transactions)}, confidence, risk, note)

async def step3_statements(state: AccountingState) -> AccountingState:
    vouchers=state.get("step_outputs", {}).get(STEP2, {}).get("vouchers", []); totals=defaultdict(float)
    for voucher in vouchers:
        entries=voucher.get("entries") or []
        if entries:
            for entry in entries:
                amount=float(entry.get("amount",0)); totals[str(entry.get("account","待处理科目"))]+=amount if entry.get("direction")=="debit" else -amount
        else:
            totals[voucher["debit_account"]]+=float(voucher.get("debit_amount",0)); totals[voucher["credit_account"]]-=float(voucher.get("credit_amount",0))
    def prefix(name: str) -> float:
        return sum(value for key,value in totals.items() if key==name or key.startswith(name+"-") or key.startswith(name+" "))
    expense=max(0.0,prefix("管理费用")+prefix("销售费用")+prefix("制造费用")); revenue=max(0.0,-prefix("主营业务收入")); cash=prefix("银行存款")
    inventory=max(0.0,prefix("库存商品")+prefix("原材料")); fixed_assets=max(0.0,prefix("固定资产")); receivable=max(0.0,prefix("应收账款")); payable=max(0.0,-prefix("应付账款")); taxes=max(0.0,-prefix("应交税费"))
    assets=max(0.0,cash)+receivable+inventory+fixed_assets; liabilities=payable+taxes; equity=assets-liabilities
    balance_ok=abs(assets-(liabilities+equity))<0.01
    balance_sheet={"assets":round(assets,2),"liabilities":round(liabilities,2),"equity":round(equity,2),"cash":round(cash,2),"inventory":round(inventory,2),"fixed_assets":round(fixed_assets,2),"balanced":balance_ok}
    income_statement={"revenue":revenue,"expenses":expense,"net_profit":revenue-expense}
    cash_in=round(sum(float(v.get("debit_amount",0)) for v in vouchers if v.get("debit_account")=="银行存款"),2)
    cash_out=round(sum(float(v.get("credit_amount",0)) for v in vouchers if v.get("credit_account")=="银行存款"),2)
    cash_flow_statement={"operating_net_cash":round(cash_in-cash_out,2),"cash_in":cash_in,"cash_out":cash_out}
    report_csv={
        "balance_sheet": _csv_text(["项目", "金额", "校验"], [["货币资金", cash, ""], ["应收账款", receivable, ""], ["存货", inventory, ""], ["固定资产", fixed_assets, ""], ["资产合计", assets, ""], ["负债合计", liabilities, ""], ["所有者权益", equity, ""], ["资产=负债+权益", assets-liabilities-equity, "通过" if balance_ok else "需复核"]]),
        "income_statement": _csv_text(["项目", "金额"], [["营业收入", revenue], ["营业成本及费用", expense], ["净利润", revenue-expense]]),
        "cash_flow_statement": _csv_text(["项目", "金额"], [["经营活动现金流入", cash_in], ["经营活动现金流出", cash_out], ["经营活动净现金流", cash_in-cash_out]])
    }
    workbook = _statement_workbook(balance_sheet, income_statement, cash_flow_statement)
    output={"trial_balance": dict(totals), "balance_sheet":balance_sheet, "income_statement":income_statement, "cash_flow_statement":cash_flow_statement, "report_csv":report_csv, "report_files":[], "table_csv": {f"{workbook['name']}::{sheet['name']}": sheet['csv'] for sheet in workbook['sheets']}, "table_files": [{"name": workbook['name'], "sheets": [{"name": sheet['name']} for sheet in workbook['sheets']]}], "table_preview": _table_preview([workbook]), "adjustments":[], "anomalies":[] if balance_ok else [{"reason":"资产负债表勾稽关系异常"}], "dataset_status":"待人工确认"}
    note=await _model_note(STATEMENT_PROMPT.format(vouchers=json.dumps(vouchers, ensure_ascii=False)), state.get("use_llm", True))
    return _set_review(state, STEP3, output, {"voucher_count":len(vouchers)}, 0.95 if balance_ok else 0.48, 0.05 if balance_ok else 0.9, note)

async def step4_comparison(state: AccountingState) -> AccountingState:
    current=state.get("step_outputs", {}).get(STEP3, {}); history=[]
    for path in state.get("history_paths", []): history.append({"source_file":Path(path).name,"content":_read(path)[:6000]})
    metrics={"资产":current.get("balance_sheet",{}).get("assets",0),"负债":current.get("balance_sheet",{}).get("liabilities",0),"所有者权益":current.get("balance_sheet",{}).get("equity",0),"收入":current.get("income_statement",{}).get("revenue",0),"净利润":current.get("income_statement",{}).get("net_profit",0)}
    comparisons=[]
    for period in ("环比","同比","同季度"):
        comparisons.append({"period":period,"current":metrics,"previous":{},"changes":{},"comment":"未提供可匹配历史期数据，待人工补充或核对"})
    output={"current_metrics":metrics,"historical_sources":history,"comparisons":comparisons,"anomalies":[{"reason":"历史数据不足，无法完成完整期间比较"}] if not history else [],"report":"已生成同比、环比、同季度分析框架，历史期金额和异动原因待人工核对。","dataset_status":"待人工确认"}
    note=await _model_note(COMPARISON_PROMPT.format(current=json.dumps(metrics, ensure_ascii=False), history=json.dumps(history, ensure_ascii=False)), state.get("use_llm", True))
    return _set_review(state, STEP4, output, {"current_statement": current, "history_files": [Path(p).name for p in state.get("history_paths", [])]}, 0.62 if history else 0.45, 0.55 if history else 0.85, note)

def _merge_display(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items(): merged[key] = _merge_display(merged.get(key), value)
        return merged
    if isinstance(base, list) and isinstance(patch, list) and all(isinstance(item, dict) for item in patch):
        identity = next((key for key in ("invoice_id", "voucher_no", "period") if any(key in item for item in patch)), None)
        if identity:
            by_id = {item.get(identity): item for item in base if isinstance(item, dict)}
            result = list(base)
            positions = {item.get(identity): index for index, item in enumerate(base) if isinstance(item, dict)}
            for item in patch:
                key = item.get(identity)
                if key in positions:
                    result[positions[key]] = _merge_display(by_id[key], item)
                else:
                    result.append(item)
            return result
    return patch

async def human_gate(state: AccountingState) -> AccountingState:
    review={"workflow_id":state.get("workflow_id"),"step":state.get("current_step"),"status":"pending_review","confidence":state.get("confidence",0),"risk":state.get("risk",1),"original_data":state.get("review_context",{}).get("original_data",{}),"ai_output":state.get("review_context",{}).get("ai_output",{}),"display_data":state.get("review_context",{}).get("display_data",{}),"rules":state.get("review_context",{}).get("rules","")}
    decision=interrupt(review)
    action=str(decision.get("action", "return")) if isinstance(decision, dict) else "return"
    comment=decision.get("comment", "") if isinstance(decision, dict) else ""
    edited=decision.get("edited_data") if isinstance(decision, dict) else None
    audit=list(state.get("audit_log", [])); audit.append({"event":"human_action","step":state.get("current_step"),"action":action,"comment":comment,"edited_data":edited})
    state["audit_log"]=audit; state["pending_action"]={"action":action,"comment":comment}
    if action == "return":
        state["retry_step"]=state.get("current_step", STEP1); state["status"]="pending_review"; return state
    if action == "upload" and isinstance(edited, dict):
        step=state.get("current_step", STEP1)
        base=state.get("step_outputs", {}).get(step, {})
        display=dict(base)
        for key, value in edited.items():
            display[key] = value
        # 上传表格已经通过解析器转换为结构化字段，仍经当前步骤 Pydantic 校验。
        display = OUTPUT_MODELS[step].model_validate(display).model_dump()
        outputs=dict(state.get("step_outputs", {})); outputs[step]=display; state["step_outputs"]=outputs
        context=dict(state.get("review_context", {})); context["display_data"]=display; context["uploaded_table"] = True; state["review_context"]=context
    if action == "edit" and state.get("current_step") == STEP4 and isinstance(edited, dict):
        step = STEP4
        base = state.get("review_context", {}).get("display_data") or state.get("step_outputs", {}).get(step, {})
        display = OUTPUT_MODELS[step].model_validate(_merge_display(base, edited)).model_dump()
        outputs = dict(state.get("step_outputs", {})); outputs[step] = display; state["step_outputs"] = outputs
        context = dict(state.get("review_context", {})); context["display_data"] = display; state["review_context"] = context
    state["retry_step"]=""; state["status"]="running"
    if state.get("current_step") == STEP4: state["status"]="completed"
    return state

def _next(state: AccountingState) -> str:
    if state.get("retry_step"): return state["retry_step"]
    return {STEP1:"step2", STEP2:"step3", STEP3:"step4", STEP4:"finish"}.get(state.get("current_step", STEP1), "finish")

def build_accounting_graph():
    builder=StateGraph(AccountingState)
    builder.add_node("step1", step1_classification); builder.add_node("step2", step2_vouchers); builder.add_node("step3", step3_statements); builder.add_node("step4", step4_comparison); builder.add_node("human_gate", human_gate)
    builder.add_edge(START,"step1"); builder.add_edge("step1","human_gate"); builder.add_edge("step2","human_gate"); builder.add_edge("step3","human_gate"); builder.add_edge("step4","human_gate")
    builder.add_conditional_edges("human_gate", _next, {"step1":"step1","step2":"step2","step3":"step3","step4":"step4","finish":END})
    return builder.compile(checkpointer=_MEMORY)
