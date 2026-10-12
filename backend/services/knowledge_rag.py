"""隔离知识库 RAG 服务。

PostgreSQL 保存原始 chunk，提供 BM25 风格关键词召回；Milvus 使用同一 collection 的独立
partition 保存向量。最终分数严格按 0.5*BM25 + 0.5*向量相似度归一化合并。
"""
from __future__ import annotations
import math, re, time
from dataclasses import dataclass
from typing import Any

TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")

def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]

def _normalize(values: list[float]) -> list[float]:
    if not values: return []
    low, high = min(values), max(values)
    if high - low < 1e-9: return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]

def _bm25(query: list[str], content: str, avg_len: float, total_docs: int, document_freq: dict[str, int]) -> float:
    terms = tokenize(content); tf: dict[str, int] = {}
    for term in terms: tf[term] = tf.get(term, 0) + 1
    k1, b = 1.5, 0.75
    score = 0.0
    for term in set(query):
        if term not in tf: continue
        df = document_freq.get(term, 0)
        idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
        score += idf * (tf[term] * (k1 + 1)) / (tf[term] + k1 * (1 - b + b * len(terms) / max(avg_len, 1)))
    return score

class IsolatedKnowledgeRAG:
    COLLECTION = "knowledge_domain"

    @staticmethod
    def partition_name(knowledge_base_id: str) -> str:
        # Milvus partition名只使用安全字符，避免把用户输入拼入表达式。
        return "kb_" + re.sub(r"[^a-zA-Z0-9_]", "", knowledge_base_id.replace("-", ""))[:50]

    @classmethod
    def _partition(cls, knowledge_base_id: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_]", "", knowledge_base_id.replace("-", ""))
        return "kb_" + clean[:50]

    @classmethod
    def _client(cls):
        from backend.core.knowledge_base import KnowledgeBaseClient
        return KnowledgeBaseClient()._client

    @classmethod
    def ensure_partition(cls, partition: str) -> bool:
        try:
            client = cls._client()
            if not client.has_partition(collection_name=cls.COLLECTION, partition_name=partition):
                client.create_partition(collection_name=cls.COLLECTION, partition_name=partition)
            return True
        except Exception:
            return False

    @classmethod
    def upsert_vectors(cls, knowledge_base_id: str, document_id: str, source_name: str, chunks: list[str], tenant_id: str) -> int:
        if not chunks: return 0
        from backend.core.knowledge_base import BGEMEmbedder
        dense, sparse = BGEMEmbedder.get_instance().encode(chunks)
        partition = cls._partition(knowledge_base_id)
        if not cls.ensure_partition(partition):
            raise RuntimeError("Milvus collection 或知识库 partition 不可用，请先初始化 Milvus")
        rows=[]
        for index, content in enumerate(chunks):
            rows.append({"id": f"{document_id}_{index}", "embedding": dense[index], "sparse_embedding": sparse[index],
                "content": content[:4096], "chunk_index": index, "document_id": document_id,
                "course_id": "studio", "knowledge_base_id": knowledge_base_id, "tenant_id": tenant_id,
                "source_name": source_name, "chunk_type": "text", "version": "1", "updated_at": int(time.time())})
        client=cls._client()
        try:
            client.upsert(collection_name=cls.COLLECTION, partition_name=partition, data=rows)
        except TypeError:
            client.upsert(collection_name=cls.COLLECTION, data=rows, partition_name=partition)
        return len(rows)

    @classmethod
    def delete_document_vectors(cls, knowledge_base_id: str, document_id: str) -> None:
        try:
            client=cls._client(); partition=cls._partition(knowledge_base_id)
            client.delete(collection_name=cls.COLLECTION, partition_name=partition, filter=f'document_id == "{document_id}"')
        except Exception:
            pass

    @classmethod
    def vector_search(cls, knowledge_base_id: str, query_dense: list[float], top_k: int) -> list[dict[str, Any]]:
        try:
            client=cls._client(); partition=cls._partition(knowledge_base_id)
            if not cls.ensure_partition(partition): return []
            result=client.search(collection_name=cls.COLLECTION, data=[query_dense], anns_field="embedding",
                search_params={"metric_type":"COSINE", "params":{"ef":64}}, limit=top_k,
                output_fields=["content","document_id","source_name","chunk_index","knowledge_base_id"], partition_names=[partition])
            hits=result[0] if result else []
            return [{"id": str(hit.get("id", "")), "vector_score": float(hit.get("distance", hit.get("score", 0))), **(hit.get("entity") or {})} for hit in hits]
        except Exception:
            return []

    @classmethod
    async def search(cls, db, knowledge_base_id: str, query: str, top_k: int = 6) -> list[dict[str, Any]]:
        from sqlalchemy import text
        rows=(await db.execute(text("""SELECT c.id, c.content, c.chunk_index, d.source_name, c.document_id
            FROM knowledge_document_chunks c JOIN knowledge_documents d ON d.id=c.document_id
            WHERE c.knowledge_base_id=:kb AND d.knowledge_base_id=:kb AND d.status='ready'"""), {"kb":knowledge_base_id})).mappings().all()
        docs=[dict(row) for row in rows]; query_terms=tokenize(query); total=len(docs)
        df={term:sum(1 for doc in docs if term in set(tokenize(doc["content"]))) for term in set(query_terms)}
        avg=sum(len(tokenize(doc["content"])) for doc in docs)/max(total,1)
        bm25=[_bm25(query_terms,doc["content"],avg,total,df) for doc in docs]
        bm25_norm=_normalize(bm25); vector=[]
        try:
            from backend.core.knowledge_base import BGEMEmbedder
            dense,_=await __import__('asyncio').to_thread(BGEMEmbedder.get_instance().encode_query, query)
            vector=await __import__('asyncio').to_thread(cls.vector_search, knowledge_base_id, dense, max(top_k*3,10))
        except Exception: vector=[]
        vector_by_doc={str(item.get("document_id"))+":"+str(item.get("chunk_index")): item.get("vector_score",0) for item in vector}
        vector_scores=[float(vector_by_doc.get(str(doc["document_id"])+":"+str(doc["chunk_index"]),0)) for doc in docs]
        vector_norm=_normalize(vector_scores)
        merged=[]
        for index,doc in enumerate(docs):
            score=0.5*bm25_norm[index]+0.5*vector_norm[index]
            merged.append({"content":doc["content"],"score":round(score,6),"bm25_score":round(bm25_norm[index],6),"vector_score":round(vector_norm[index],6),"metadata":{"source_name":doc["source_name"],"document_id":str(doc["document_id"]),"knowledge_base_id":knowledge_base_id,"chunk_index":doc["chunk_index"]}})
        return sorted(merged,key=lambda item:item["score"],reverse=True)[:top_k]


