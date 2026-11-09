"""Cognito custom email content. Never log the event or call SES directly."""

SUBJECTS = {
    "CustomMessage_SignUp": ("Xác minh tài khoản", "Verify your account"),
    "CustomMessage_ResendCode": ("Mã xác minh mới", "New verification code"),
    "CustomMessage_ForgotPassword": ("Đặt lại mật khẩu", "Reset your password"),
    "CustomMessage_Authentication": ("Mã xác thực", "Authentication code"),
    "CustomMessage_UpdateUserAttribute": ("Xác minh thông tin tài khoản", "Verify your account information"),
    "CustomMessage_VerifyUserAttribute": ("Xác minh thông tin tài khoản", "Verify your account information"),
    "CustomMessage_AdminCreateUser": ("Lời mời HomeWallet", "HomeWallet invitation"),
}


def handler(event, context):
    request = event.get("request", {})
    source = event.get("triggerSource")
    code = request.get("codeParameter")
    if source not in SUBJECTS or not code:
        return event

    english = request.get("userAttributes", {}).get("custom:preferred_locale") == "en"
    subject = SUBJECTS[source][int(english)]
    if source == "CustomMessage_AdminCreateUser":
        username = request.get("usernameParameter")
        if not username:
            return event
        message = (
            f"Your HomeWallet username is {username}. Your temporary password is {code}."
            if english else
            f"Tên đăng nhập HomeWallet của bạn là {username}. Mật khẩu tạm thời là {code}."
        )
    elif source == "CustomMessage_ForgotPassword":
        message = (
            f"Your HomeWallet password reset code is: {code}"
            if english else f"Mã đặt lại mật khẩu HomeWallet của bạn là: {code}"
        )
    else:
        message = (
            f"Your HomeWallet code is: {code}"
            if english else f"Mã HomeWallet của bạn là: {code}"
        )

    response = event.setdefault("response", {})
    response["emailSubject"] = f"HomeWallet - {subject}"
    response["emailMessage"] = message
    return event
