import asyncio
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta, datetime
from functools import partial
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.command_router import CommandContext, CommandRouter, OutboundMessage
from app.logging_setup import setup_logging
from app.wechat.WXBizMsgCrypt import WXBizMsgCrypt, WeComReceiverConfig
from app.wechat.wecom_sender import WeComSender, WeComSenderConfig


@dataclass(frozen=True)
class Settings:
    token: str
    encoding_aes_key: Optional[str]
    corp_id: Optional[str]
    agent_secret: Optional[str]
    agent_id: Optional[str]

    @property
    def has_crypto(self) -> bool:
        return bool(self.encoding_aes_key)

    @property
    def has_sender(self) -> bool:
        return bool(self.corp_id and self.agent_secret and self.agent_id)


logger = setup_logging(
    log_dir=os.getenv("LOG_DIR", "logs"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    backup_days=os.getenv("LOG_BACKUP_DAYS", "30"),
)


def load_settings() -> Settings:
    corp_id = os.getenv("WECOM_CORP_ID", "")
    token = os.getenv("WECOM_TOKEN", "")
    encoding_aes_key = os.getenv("WECOM_ENCODING_AES_KEY", "")
    agent_id = os.getenv("WECOM_AGENT_ID", "")
    agent_secret = os.getenv("WECOM_AGENT_SECRET", "")

    if not token:
        logger.error("WECOM_TOKEN is missing")
        raise RuntimeError("WECOM_TOKEN is required")
    if not corp_id:
        logger.error("WECOM_CORP_ID is missing")
        raise RuntimeError("WECOM_RECEIVE_ID is required")

    return Settings(
        token=token,
        encoding_aes_key=encoding_aes_key or None,
        corp_id=corp_id or None,
        agent_secret=agent_secret or None,
        agent_id=agent_id or None,
    )


def xml_to_dict(xml_text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.exception("Failed to parse XML payload")
        raise ValueError("invalid xml payload") from exc
    return {child.tag: (child.text or "") for child in root}


def cdata_safe(text: str) -> str:
    return text.replace("]]>", "]]]]><![CDATA[>")


# 创建一个起始时间（Unix时间起点）
epoch = datetime(1970, 1, 1, tzinfo=ZoneInfo("UTC"))
# 东八区
tz = ZoneInfo("Asia/Shanghai")
# 时间戳格式
time_fmt = '%Y-%m-%d %H:%M:%S'


def format_time(time_second):
    # 将秒数转换为timedelta对象
    time_since_epoch = timedelta(seconds=time_second)
    # 将时间差加到起始时间上
    formatted_time = epoch + time_since_epoch
    # 格式化日期和时间
    return formatted_time.astimezone(tz=tz).strftime(time_fmt)


settings = load_settings()
router = CommandRouter()
crypto = (
    WXBizMsgCrypt(
        WeComReceiverConfig(
            corp_id=settings.corp_id,
            token=settings.token,
            encoding_aes_key=settings.encoding_aes_key,
        )
    )
    if settings.has_crypto
    else None
)
sender = (
    WeComSender(
        WeComSenderConfig(
            corp_id=settings.corp_id,
            agent_secret=settings.agent_secret,
            agent_id=settings.agent_id,
        )
    )
    if settings.has_sender
    else None
)
app = FastAPI(title="WeCom Command Service")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/wecom/callback")
def verify_wecom_url(
        msg_signature: str = Query(default=""),
        timestamp: str = Query(default=""),
        nonce: str = Query(default=""),
        echostr: str = Query(default=""),
) -> PlainTextResponse:
    if not echostr:
        logger.warning("URL verify failed: missing echostr")
        raise HTTPException(status_code=400, detail="echostr is required")

    if msg_signature and crypto:
        try:
            ret, sEchoStr = crypto.VerifyURL(msg_signature, timestamp, nonce, echostr)
            if ret != 0:
                logger.error("URL verify failed: decrypt echostr error")
                raise HTTPException(status_code=400, detail=f"URL verify failed: ret: {ret}")
            else:
                return PlainTextResponse(content=sEchoStr)
        except Exception as exc:
            logger.exception("URL verify failed: decrypt echostr error")
            raise HTTPException(status_code=400, detail=f"verify failed: {exc}") from exc

    if msg_signature and not crypto:
        logger.error("URL verify failed: encrypted request but crypto is disabled")
        raise HTTPException(status_code=400, detail="encrypted mode requested but crypto is disabled")

    return PlainTextResponse(content=echostr)


@app.post("/wecom/callback")
async def wecom_callback(
        request: Request,
        msg_signature: str = Query(default=""),
        timestamp: str = Query(default=""),
        nonce: str = Query(default=""),
) -> Response:
    raw_xml = (await request.body()).decode("utf-8")
    if not raw_xml:
        logger.warning("Message callback failed: request body is empty")
        raise HTTPException(status_code=400, detail="request body is empty")

    try:
        ret, sMsg = crypto.DecryptMsg(raw_xml, msg_signature, timestamp, nonce)
        if ret != 0:
            logger.error("Message callback failed: decrypt message error")
            raise HTTPException(status_code=400, detail=f"decrypt failed: ret: {ret}")
        xml_data = xml_to_dict(sMsg)
        logger.debug(f"Received message {xml_data}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fromUser = xml_data.get("FromUserName", "")
    toUser = xml_data.get("ToUserName", "")
    creatTime = xml_data.get("CreateTime", "")
    msgId = xml_data.get("MsgId", "")
    agentId = xml_data.get("AgentID", "")
    sessionFrom = xml_data.get("SessionFrom", "")
    msgType = xml_data.get("MsgType", "")
    event = xml_data.get("Event", "")
    content = xml_data.get("Content", "")
    msg_time = None
    if creatTime is not None:
        try:
            msg_time = format_time(int(creatTime))
        except:
            pass

    logger.info(f"Received message {content} from {fromUser} at {msg_time}")
    if msgType != "text":
        return PlainTextResponse("success")

    asyncio.create_task(handle_command_and_notify(from_user=fromUser, content=content))
    return PlainTextResponse("success")


async def handle_command_and_notify(from_user: str, content: str) -> None:
    try:
        await router.dispatch(
            CommandContext(
                user_id=from_user,
                content=content,
                send_message=send_message_to_user,
            )
        )
    except Exception:
        logger.exception("Async command dispatch failed, user=%s, content=%s", from_user, content)
        return

    logger.info("Async command completed, user=%s", from_user)


async def send_message_to_user(to_user: str, message: OutboundMessage) -> None:
    if not sender:
        logger.warning("Message sender is not configured, skip notify user=%s", to_user)
        return

    try:
        msg_type = message.msg_type.lower()
        payload = message.payload

        if msg_type == "text":
            call = partial(sender.send_text, message=payload["content"], touser=to_user)
            await asyncio.to_thread(call)
        elif msg_type == "markdown":
            call = partial(sender.send_markdown, message=payload["content"], touser=to_user)
            await asyncio.to_thread(call)
        elif msg_type == "textcard":
            call = partial(
                sender.send_textcard,
                card_title=payload["title"],
                desc=payload["description"],
                link=payload["url"],
                btn=payload.get("btn", "详情"),
                touser=to_user,
            )
            await asyncio.to_thread(call)
        elif msg_type == "image":
            call = partial(sender.send_image, iamge_path=payload["media_path"], touser=to_user)
            await asyncio.to_thread(call)
        elif msg_type == "voice":
            call = partial(sender.send_voice, voice_path=payload["voice_path"], touser=to_user)
            await asyncio.to_thread(call)
        elif msg_type == "video":
            call = partial(
                sender.send_video,
                video_path=payload["video_path"],
                title=payload.get("title"),
                desc=payload.get("description"),
                touser=to_user,
            )
            await asyncio.to_thread(call)
        elif msg_type == "file":
            call = partial(sender.send_file, file_path=payload["file_path"], touser=to_user)
            await asyncio.to_thread(call)
        elif msg_type == "news":
            if "articles" in payload:
                call = partial(sender.send_graphic_list, articles=payload["articles"], touser=to_user)
                await asyncio.to_thread(call)
            else:
                call = partial(
                    sender.send_graphic,
                    card_title=payload["title"],
                    desc=payload["description"],
                    link=payload["url"],
                    image_link=payload["image_url"],
                    touser=to_user,
                )
                await asyncio.to_thread(call)
        elif msg_type in ("miniprogram_notice", "mini_program"):
            call = partial(
                sender.send_mini_program,
                title=payload["title"],
                description=payload["description"],
                content_item=payload["content_item"],
                emphasis_first_item=payload.get("emphasis_first_item", False),
                appid=payload["appid"],
                page=payload["page"],
                touser=to_user,
            )
            await asyncio.to_thread(call)
        else:
            raise ValueError(f"unsupported message type: {message.msg_type}")
    except Exception:
        logger.exception("Send async reply failed, user=%s, msg_type=%s", to_user, message.msg_type)
