import os
import time
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
import configparser
from .api import chat_api
import requests

from app.wechat.logger import get_wechat_logger


class WorkChatApi(ABC):
    """
    接口类，定义所有的接口
    """

    @abstractmethod
    def get_token(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_text(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_markdown(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_image(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_voice(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_video(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_file(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_textcard(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_graphic(self, *args, **kwargs):
        pass

    @abstractmethod
    def send_graphic_list(self, *args, **kwargs):
        pass

    @abstractmethod
    def upload_image(self, *args, **kwargs):
        pass

    @abstractmethod
    def get_users_id(self, *args, **kwargs):
        pass


tokenp = Path.cwd().joinpath(".token")
logger = get_wechat_logger()
DEFAULT_HTTP_TIMEOUT = float(os.getenv("WECOM_HTTP_TIMEOUT", "10"))


class HandlerTool:
    """
    处理类，封装请求，处理请求以及请求闭环。为上层接口提供处理逻辑
    """

    def __init__(self, corpid=None, corpsecret=None, agentid=None, **kwargs):
        self.corpid = corpid
        self.corpsecret = corpsecret
        self.agentid = agentid
        self._op = None
        self.url = 'https://qyapi.weixin.qq.com'
        self.http_timeout = float(kwargs.pop("timeout", DEFAULT_HTTP_TIMEOUT))
        self.conf = configparser.ConfigParser()
        self.judgment_type(corpid, corpsecret, agentid, **kwargs)
        self.token = self.get_token()
        # logging.info(f'init token {self.token}')

    @staticmethod
    def is_image(file):

        if not (file.suffix in (".JPG", ".PNG", ".jpg", ".png") and (5 <= file.stat().st_size <= 2 * 1024 * 1024)):
            raise TypeError(
                {"Code": "ERROR", "message": '图片文件不合法, 请检查文件类型(jpg, png, JPG, PNG)或文件大小(5B~2M)'})

    @staticmethod
    def is_voice(file):

        if not (file.suffix in (".AMR", ".amr") and (5 <= file.stat().st_size <= 2 * 1024 * 1024)):
            raise TypeError({"Code": "ERROR", "message": '语音文件不合法, 请检查文件类型(AMR, amr)或文件大小(5B~2M)'})

    @staticmethod
    def is_video(file):

        if not (file.suffix in (".MP4", ".mp4") and (5 <= file.stat().st_size <= 10 * 1024 * 1024)):
            raise TypeError({"Code": "ERROR", "message": '视频文件不合法, 请检查文件类型(MP4, mp4)或文件大小(5B~10M)'})

    @staticmethod
    def is_file(file):
        if not (file.is_file() and (5 <= file.stat().st_size <= 10 * 1024 * 1024)):
            raise TypeError({"Code": "ERROR", "message": '普通文件不合法, 请检查文件类型或文件大小(5B~10M)'})

    def judgment_type(self, corpid, corpsecret, agentid, path=Path.cwd().joinpath('.chatkey.conf')):

        # 传入cid，Path未传就直接返回,若其中一个为None 则报错。
        # 传入path, cid 未传。 判断path是否是一个正常的文件若不是 则报错
        # 未传入cid,path，则检查默认目录是否存在chatkey.info 有就读，无则创建

        if corpid and corpsecret and agentid:
            self.corpid = corpid
            self.corpsecret = corpsecret
            self.agentid = agentid

        elif corpid or corpsecret or agentid:

            raise TypeError({"Code": 'ERROR', "message": 'corpid, corpsecret, agentid 参数有误, 请检查'})

        else:
            if Path(path).is_file():
                self.conf.read(path, encoding="utf-8")
                self.corpid = self.conf.get("chatinfo", "corpid")
                self.corpsecret = self.conf.get("chatinfo", "corpsecret")
                self.agentid = self.conf.get("chatinfo", "agentid")
                self.conf.clear()

            elif path != Path.cwd().joinpath('.chatkey.conf'):
                raise TypeError({"Code": 'ERROR', "message": '传入的路径不是一个正常的文件，请检查'})

            else:
                self.corpid = input("请输入corpid:\n").strip()
                self.corpsecret = input("请输入corpsecret:\n").strip()
                self.agentid = input("请输入agentid:\n").strip()
                self.get_token()
                with open(str(path), 'w', encoding="utf-8") as fp:
                    self.conf["chatinfo"] = {"corpid": self.corpid, "corpsecret": self.corpsecret,
                                             "agentid": self.agentid}
                    self.conf.write(fp)
                    self.conf.clear()

    def file_check(self, file_type, path):
        """
        验证上传文件是否符合标准
        :param file_type: 文件类型(image,voice,video,file)
        :param path:
        :return:
        """

        p = Path(path)
        filetypes = {"image": self.is_image, "voice": self.is_voice, "video": self.is_video, "file": self.is_file}

        chack_type = filetypes.get(file_type, None)

        if not chack_type:
            raise TypeError({"Code": 'ERROR', "message": '不支持的文件类型，请检查文件类型(image,voice,video,file)'})

        chack_type(p)
        return {"file": (p.name, p.read_bytes())}

    def _get(self, uri, **kwargs):
        """
        发起get请求
        :param uri: 需要请求的Url
        :param kwargs: 需要带入的参数
        :return:
        """

        try:
            rsp = requests.get(self.url + uri, timeout=self.http_timeout, **kwargs)
            rsp.raise_for_status()
            result = rsp.json()
            errcode = result.get("errcode")
            if errcode in (None, 0):
                return result

            if errcode in (40013, 40001):
                raise ValueError({"Code": result.get("errcode"), "message": "输入的corpid 或 corpsecret错误请检查"})
            logger.warning("wechat _get returned non-zero result: %s", result)
            return result

        except requests.RequestException as e:
            logger.exception("wechat _get request failed: %s", e)
            raise

    def _post(self, uri, **kwargs):
        """
        发起Post请求
        :param uri: 需要请求的Url
        :param kwargs: 请求所需的参数
        :return:
        """
        try:
            url = self.url + uri
            for i in range(2):
                rsp = requests.post(url.format(self.token), timeout=self.http_timeout, **kwargs)
                rsp.raise_for_status()
                result = rsp.json()
                logger.debug('request %s send wechat notify result: %s', i, result)
                if result.get("errcode") == 0:
                    return result
                elif result.get("errcode") == 42001 or result.get("errcode") == 40014:
                    logger.info('request %s token失效，重新获取', i)
                    self.token = self._get_token()
                    logger.info('get token %s', self.token)
                else:
                    logger.warning('request %s 消息发送失败！原因: %s', i, rsp.text)
                    return result
        except requests.exceptions.HTTPError as HTTPError:
            logger.exception('send wechat notify HTTPError: %s', HTTPError)
            raise requests.exceptions.HTTPError(
                f"发送失败， HTTP error:{HTTPError.response.status_code} , 原因: {HTTPError.response.reason}")
        except requests.exceptions.ConnectionError as e:
            logger.exception('send wechat notify ConnectionError: %s', e)
            raise requests.exceptions.ConnectionError("发送失败，HTTP connection error!")
        except requests.exceptions.Timeout as e:
            logger.exception('send wechat notify Timeout: %s', e)
            raise requests.exceptions.Timeout("发送失败，Timeout error!")
        except requests.exceptions.RequestException as e:
            logger.exception('send wechat notify RequestException: %s', e)
            raise requests.exceptions.RequestException("发送失败, Request Exception!")

    def get_token(self):
        """
        获取token
        :return:
        """

        # 先读文件如果没有就发起请求并写入文件返回，有就判断timeout失效就发起请求并写入文件返回，时效正常直接返回
        self._op = hashlib.md5(bytes(self.corpsecret + self.corpid, encoding='utf-8')).hexdigest()

        if tokenp.is_file():
            self.conf.read(tokenp, encoding="utf-8")

            try:
                if not int(time.time()) > int(self.conf.get(self._op, "tokenout")):
                    return self.conf.get(self._op, "token")

                logger.info("token失效，重新获取...")
            except (configparser.NoSectionError, configparser.NoOptionError):
                logger.warning({"Code": 'ERROR', "message": f'未读取到 {self._op} 节点或节点下的tokenout, 重新获取..'})

            except ValueError:
                logger.warning(
                    {"Code": 'ERROR', "message": f'请检查 {self._op} 下 tokenout 节点数据为空， 重新获取覆盖'})

        return self._get_token()

    def _get_token(self):

        tokenurl = chat_api.get("GET_ACCESS_TOKEN").format(self.corpid, self.corpsecret)
        rsp = self._get(tokenurl)
        if not rsp or not rsp.get("access_token"):
            raise RuntimeError(f"获取 token 失败: {rsp}")

        expires_in = int(rsp.get("expires_in", 7200))
        tokeninfo = {"token": rsp.get("access_token"), "tokenout": str(int(time.time()) + expires_in)}

        self.conf[self._op] = tokeninfo
        try:
            with open(str(tokenp), "w", encoding='utf-8') as fp:
                self.conf.write(fp)
                self.conf.clear()
                logger.info('token持久化成功.. --> %s', tokenp)

        except Exception as e:
            logger.exception("token持久化失败: %s", e)
            logger.warning({"Code": 'ERROR', "message": "token持久化失败, 请根据报错进行排查(不影响请求)"})

        return rsp.get("access_token")

    def send_message(self, message_type, message, touser=None, todept=None, totags=None):
        """
        发送消息的主要接口封装和发起请求
        :param message_type: 发送消息的类型
        :param message: 发送消息的内容
        :param touser: 发送到具体的用户，当此参数为@all时，忽略todept,totags 参数并发送到全部人，此参数默认为@all
        用户名用 | 拼接。最多支持100个
        :param todept: 发送到部门，当tousers为默认@all 此参数会被忽略.部门之间用 | 拼接。最多支持100个
        :param totags: 发送到标签的用用户,当tousers为默认@all 此参数会被忽略. 标签之间用 | 拼接.最多支持100个
        :return:
        """
        data = {
            "msgtype": message_type,
            "agentid": self.agentid,
            message_type: message
        }

        if not (touser or todept or totags):
            data["touser"] = "@all"

        else:
            if touser:
                data["touser"] = touser

            if todept:
                data["toparty"] = todept

            if totags:
                data["totag"] = totags

        # 判断是否需要上传
        if message_type in ("image", "voice", "video", "file"):
            filepath = message.get("media_id")

            media_id = self.upload_media(message_type, filepath)
            message["media_id"] = media_id

        target = data.get("touser") or data.get("toparty") or data.get("totag") or "@all"
        logger.info("发送 %s %s --> %s", message_type, message, target)
        return self._post(chat_api.get('MESSAGE_SEND'), json=data)

    def upload_media(self, file_type, path):
        """
        上传临时素材， 3天有效期
        :param file_type: 文件类型
        :param path: 文件路
        :return: media_id
        """

        fileinfo = self.file_check(file_type, path)
        rsp = self._post(chat_api.get("MEDIA_UPLOAD").format("{}", file_type), files=fileinfo)
        return rsp.get("media_id")

    def upload_image(self, picture_path, enable=True):
        """
        上传图片，返回图片url，url永久有效
        图片大小：图片文件大小应在 5B ~ 2MB 之间
        :param picture_path:  图片路径
        :param enable:  是否开启上传记录
        :return: 图片url，永久有效
        """

        p_imag = Path(picture_path)

        if not p_imag.is_file() or p_imag.stat().st_size > 2 * 1024 * 1024 or p_imag.stat().st_size <= 5:
            raise TypeError({"error": 'ERROR', "message": '指向的文件不是一个正常的图片或图片大小未在5B ~ 2MB之间',
                             "massage": f"{p_imag.name}: {p_imag.stat().st_size} B"})
        files = {"file": p_imag.read_bytes(), "filename": p_imag.name}

        rsp = self._post(chat_api.get("IMG_UPLOAD"), files=files)
        logger.info("图片上传成功...")
        if enable:
            with open('./imagesList.txt', "a+", encoding='utf-8') as fp:
                fp.write(f"{p_imag.name}: {rsp.get('url')}\n")

        return rsp.get("url")

    def get_departments(self, department_id):
        url = chat_api.get("GET_DEPARTMENTS").format(self.token)
        if department_id:
            url += f"&id={department_id}"
        department_data = self._get(url)
        # logging.info(f'get_departments succ: {department_data}')
        if department_data and "department" in department_data:
            for department in department_data["department"]:
                logger.info("department: %s", department)

    def get_user_info(self, user_id):
        url = chat_api.get("GET_USER_INFO").format(self.token, user_id)
        user_data = self._get(url)
        logger.info('get_user_info: %s', user_data)

    def get_users_id(self, data):
        data["access_token"] = self.token
        rsp_users = self._get(chat_api.get('GET_USERS'), params=data)
        # logging.info(f'get_users_id users: {rsp_users}')
        if rsp_users and "userlist" in rsp_users:
            for i in rsp_users.get("userlist"):
                logger.info(i)
