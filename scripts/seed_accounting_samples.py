"""生成会计核算四步流水线的本地演示材料。"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / "samples" / "accounting_demo"
FILES = {
    "invoice_001.txt": "发票号码：DEMO-001\n供应商：示例材料公司\n业务：采购办公材料\n金额：1000 元\n开票日期：2026-09-01\n",
    "invoice_002.txt": "发票号码：DEMO-002\n客户：示例客户\n业务：技术服务收入\n金额：6800 元\n开票日期：2026-09-03\n",
    "account_rules.txt": "采购/存货：采购、材料、商品进入库存商品或原材料。\n销售收入：销售、服务收入进入主营业务收入。\n差旅/办公：差旅、交通、办公进入管理费用。\n税费：增值税、附加税进入应交税费。\n",
    "bank_transactions.txt": "2026-09-01 支出 1000 元 采购办公材料\n2026-09-03 收入 6800 元 技术服务\n",
    "history_reports.txt": "2026-08 资产 120000 负债 40000 所有者权益 80000 收入 6200 净利润 1400\n2025-09 资产 100000 负债 38000 所有者权益 62000 收入 5500 净利润 1200\n",
}
for name, content in FILES.items():
    (ROOT / name).write_text(content, encoding="utf-8")
print(f"ACCOUNTING_SAMPLE_OK {ROOT}")
