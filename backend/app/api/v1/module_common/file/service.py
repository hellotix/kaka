import os

from fastapi import UploadFile

from app.config.setting import settings
from app.core.base_schema import DownloadFileSchema, UploadResponseSchema
from app.core.exceptions import CustomException
from app.core.logger import logger
from app.utils.upload_util import UploadUtil


class FileService:
    """文件管理服务层
    """

    @classmethod
    async def upload_service(
        cls,
        base_url: str,
        file: UploadFile,
        upload_type: str = "file",
        target_path: str | None = None,
        tenant_id: int | None = None,
    ) -> UploadResponseSchema:
        """上传文件（带租户隔离）"""
        tenant_prefix = f"tenant_{tenant_id}/" if tenant_id and tenant_id != 1 else ""

        filename, filepath, file_url = await UploadUtil.upload_file(
            file=file,
            base_url=base_url,
            upload_type=upload_type,
            target_path=f"{tenant_prefix}{target_path}" if target_path else None,
        )

        return UploadResponseSchema(
            file_path=f"{filepath}",
            file_name=filename,
            origin_name=file.filename,
            file_url=f"{file_url}",
        )

    @classmethod
    async def download_service(cls, file_path: str, tenant_id: int | None = None) -> DownloadFileSchema:
        """下载文件（带租户隔离）"""
        if not file_path:
            raise CustomException(msg="请选择要下载的文件")

        dangerous_patterns = ["../", "..\\", "\0"]
        for pattern in dangerous_patterns:
            if pattern in file_path:
                logger.error(f"检测到路径穿越攻击: {file_path}")
                raise CustomException(msg="非法的文件路径")

        upload_root = settings.UPLOAD_FILE_PATH.resolve()
        abs_path = os.path.normpath(os.path.abspath(file_path))

        if not abs_path.startswith(str(upload_root)):
            logger.error(f"路径不在上传目录内: {file_path}")
            raise CustomException(msg="非法的文件路径")

        if tenant_id and tenant_id != 1:
            tenant_prefix = f"{upload_root}/tenant_{tenant_id}"
            if not abs_path.startswith(str(tenant_prefix)):
                logger.error(f"文件不属于当前租户: {file_path}")
                raise CustomException(msg="无权访问该文件")

        if not UploadUtil.check_file_exists(abs_path):
            raise CustomException(msg="文件不存在")

        file_name = UploadUtil.download_file(abs_path)

        return DownloadFileSchema(
            file_path=abs_path,
            file_name=str(file_name),
        )
