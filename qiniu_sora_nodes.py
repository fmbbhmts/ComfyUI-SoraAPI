import time
import requests
import base64
from io import BytesIO
from PIL import Image
import numpy as np
import torch

class QiniuSoraAPINode:
    """
    一个通过调用七牛云 Sora 兼容 API 来生成视频的 ComfyUI 节点。
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": "sk-xxx"}),
                "prompt": ("STRING", {"multiline": True, "default": "A cute orange cat chasing a butterfly in a sunny garden."}),
                "seconds": (["4", "8", "12"],),
                "size": (["1280x720", "720x1280", "1024x768"],),
                "api_base_url": ("STRING", {"multiline": False, "default": "https://openai.qiniu.com/v1"}),
            },
            "optional": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_url",)
    FUNCTION = "generate_video"
    CATEGORY = "Sora API"

    def pil_to_base64(self, pil_image):
        """将 PIL.Image 对象转换为 base64 编码的字符串"""
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

    def tensor_to_pil(self, tensor):
        """将 ComfyUI 的 IMAGE tensor 转换为 PIL.Image 对象"""
        if tensor is None:
            return None
        image_np = tensor.cpu().numpy().squeeze()
        image_np = (image_np * 255).astype(np.uint8)
        return Image.fromarray(image_np)

    def generate_video(self, api_key, prompt, seconds, size, api_base_url, image=None):
        if not api_key or api_key == "sk-xxx":
            raise ValueError("错误：请输入您的七牛云 API Key。")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": "sora-2",
            "prompt": prompt,
            "seconds": seconds,
            "size": size,
        }

        # 如果有图像输入，将其转换为 base64 并添加到 payload
        if image is not None:
            print("检测到图像输入，正在处理...")
            pil_image = self.tensor_to_pil(image)
            base64_image = self.pil_to_base64(pil_image)
            payload["input_reference"] = base64_image
            print("图像处理完成，已添加到请求中。")

        # 1. 创建视频生成任务
        print("正在提交视频生成任务...")
        try:
            response = requests.post(f"{api_base_url}/videos", json=payload, headers=headers)
            response.raise_for_status()
            task_data = response.json()
            task_id = task_data.get("id")
            if not task_id:
                raise Exception(f"API 未返回任务 ID。响应: {task_data}")
            print(f"任务创建成功，任务 ID: {task_id}")
        except requests.exceptions.RequestException as e:
            error_message = f"创建任务失败: {e}"
            if e.response is not None:
                error_message += f" - 响应内容: {e.response.text}"
            print(error_message)
            raise Exception(error_message)


        # 2. 轮询任务状态直到完成或失败
        start_time = time.time()
        timeout = 300  # 设置 5 分钟超时
        while True:
            if time.time() - start_time > timeout:
                raise Exception("轮询超时，任务未在 5 分钟内完成。")

            print(f"正在查询任务状态 (ID: {task_id})...")
            try:
                status_response = requests.get(f"{api_base_url}/videos/{task_id}", headers=headers)
                status_response.raise_for_status()
                status_data = status_response.json()
                status = status_data.get("status")
                print(f"当前任务状态: {status}")

                if status == "completed":
                    video_url = status_data.get("task_result", {}).get("videos", [{}])[0].get("url")
                    if not video_url:
                        raise Exception("任务已完成但未找到视频 URL。")
                    print(f"视频生成成功！URL: {video_url}")
                    return (video_url,)
                elif status in ["failed", "cancelled"]:
                    error_info = status_data.get("error", {})
                    error_message = f"任务失败或已取消。原因: {error_info.get('message', '未知错误')}"
                    print(error_message)
                    raise Exception(error_message)

            except requests.exceptions.RequestException as e:
                 error_message = f"查询任务状态失败: {e}"
                 if e.response is not None:
                     error_message += f" - 响应内容: {e.response.text}"
                 print(error_message)
                 # 即使查询失败也继续尝试，除非是致命错误
            
            time.sleep(5) # 等待 5 秒后再次查询

# ComfyUI 加载节点所必需的字典
NODE_CLASS_MAPPINGS = {
    "QiniuSoraAPINode": QiniuSoraAPINode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "QiniuSoraAPINode": "Sora API Video Generator"
}