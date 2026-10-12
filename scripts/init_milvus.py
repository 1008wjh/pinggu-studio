# scripts/init_milvus.py
# 执行：python scripts/init_milvus.py
import os
from pymilvus import MilvusClient, DataType
from backend.config import get_settings


MILVUS_URI = f"http://{get_settings().milvus_host}:{get_settings().milvus_port}"
VECTOR_DIM = 1024                  # BGE-M3 稠密向量维度
COLLECTION_NAME = "knowledge_domain"  # 单集合，按 tenant_id + knowledge_base_id + partition 隔离


def build_schema(client: MilvusClient):
    """构建集合 schema：稠密 + 稀疏双向量 + 标量字段（含 tenant_id）。"""
    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("id",               DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("embedding",        DataType.FLOAT_VECTOR, dim=VECTOR_DIM)      # 稠密
    schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR)              # 稀疏
    schema.add_field("content",          DataType.VARCHAR, max_length=4096)
    schema.add_field("tenant_id",        DataType.VARCHAR, max_length=64)           # 多租户隔离
    schema.add_field("knowledge_base_id", DataType.VARCHAR, max_length=64)          # 知识库隔离（与 partition 双重约束）
    schema.add_field("chunk_index",      DataType.INT64)
    schema.add_field("document_id",      DataType.VARCHAR, max_length=64)
    schema.add_field("course_id",        DataType.VARCHAR, max_length=64)
    schema.add_field("source_name",      DataType.VARCHAR, max_length=256)
    schema.add_field("chunk_type",       DataType.VARCHAR, max_length=32)
    schema.add_field("version",          DataType.VARCHAR, max_length=32)
    schema.add_field("updated_at",       DataType.INT64)
    return schema


def build_index_params(client: MilvusClient):
    """构建索引：稠密 HNSW、稀疏 SPARSE_INVERTED、标量 INVERTED。"""
    ip = client.prepare_index_params()
    # 稠密向量：HNSW + COSINE（语义相似度）
    ip.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                 params={"M": 16, "efConstruction": 256})
    # 稀疏向量：SPARSE_INVERTED_INDEX + IP（内积）；drop_ratio_build 丢弃最低权重 token 省存储
    ip.add_index(field_name="sparse_embedding", index_type="SPARSE_INVERTED_INDEX",
                 metric_type="IP", params={"drop_ratio_build": 0.2})
    # 标量字段：INVERTED 索引，加速 filter 过滤
    ip.add_index(field_name="tenant_id", index_type="INVERTED")
    ip.add_index(field_name="knowledge_base_id", index_type="INVERTED")
    ip.add_index(field_name="course_id", index_type="INVERTED")
    return ip


def main():
    # Windows 默认 GBK 编码无法输出部分 Unicode 图标，使用 ASCII 日志保证脚本可执行。
    print(f"Milvus URI: {MILVUS_URI}")
    client = MilvusClient(uri=MILVUS_URI)

    if client.has_collection(COLLECTION_NAME):
        print(f"Drop old collection: {COLLECTION_NAME}")
        client.drop_collection(COLLECTION_NAME)

    # create_collection 传 index_params 会一并建索引并加载
    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=build_schema(client),
        index_params=build_index_params(client),
    )
    print(f"Collection created: {COLLECTION_NAME} (indexed and loaded)")
    print("Collections:", client.list_collections())
    print("Collection was rebuilt; import source documents again if needed.")


if __name__ == "__main__":
    main()
