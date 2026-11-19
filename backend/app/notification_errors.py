"""Allow-listed messages; raw provider responses and addresses never reach the UI."""

MESSAGES = {
    "SMTPRecipientsRefused": "Email server rejected the recipient address. Check the address or try again later.",
    "SMTPAuthenticationError": "Email delivery failed: SMTP authentication was rejected. Ask an administrator to check the email configuration.",
    "SMTPSenderRefused": "Email delivery failed: the sender address was rejected. Ask an administrator to check the sender configuration.",
    "SMTPNotSupportedError": "Email delivery failed: the server does not support the required secure connection.",
    "SMTPConnectError": "Cannot connect to the email server. Delivery will be retried.",
    "SMTPServerDisconnected": "The email server disconnected. Delivery will be retried.",
    "TimeoutError": "The notification provider timed out. Delivery will be retried.",
    "ConnectTimeout": "The notification provider timed out. Delivery will be retried.",
    "ReadTimeout": "The notification provider timed out. Delivery will be retried.",
    "ConnectError": "Cannot connect to the notification provider. Delivery will be retried.",
    "ConnectionRefusedError": "Cannot connect to the notification provider. Delivery will be retried.",
    "gaierror": "The notification server address could not be resolved. Check the provider configuration.",
    "HTTPStatusError": "The notification provider rejected the request. Ask an administrator to check the provider configuration.",
    "ValueError": "Notification delivery is not configured correctly for this channel. Ask an administrator to check the provider settings.",
}


def error_message(code, state=None):
    message = (
        MESSAGES.get(
            code, "Notification delivery failed. Ask an administrator to check the provider settings."
        )
        if code
        else None
    )
    if message and state == "dead":
        message = message.replace("Delivery will be retried.", "").strip()
        message += " Automatic retries stopped; administrator action is required."
    return message
