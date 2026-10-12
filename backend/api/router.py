"""工作室 API 路由总入口。"""
from fastapi import APIRouter
from backend.api.v1 import auth, knowledge, workspace, studio, document_review, evaluation

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["文档与表格工作台"])
api_router.include_router(studio.router, prefix="/studio", tags=["企业文档智能审查"])
api_router.include_router(document_review.router, prefix="/document-review", tags=["合同与招投标审查"])
api_router.include_router(evaluation.router, prefix="/evaluation", tags=["评测测试"])


