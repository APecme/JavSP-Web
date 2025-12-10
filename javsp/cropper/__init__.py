from javsp.cropper.interface import Cropper, DefaultCropper


def get_cropper(engine=None) -> Cropper:
    # 人脸识别裁剪功能已移除，统一使用默认裁剪器
    return DefaultCropper()

