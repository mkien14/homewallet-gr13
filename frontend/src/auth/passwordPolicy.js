// Matches infra/modules/cognito/main.tf. Login still accepts existing passwords.
export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_POLICY_MESSAGE = "Mật khẩu cần ít nhất 10 ký tự, gồm chữ hoa, chữ thường và số.";

export function passwordMeetsPolicy(value) {
  return typeof value === "string" && value.length >= PASSWORD_MIN_LENGTH
    && /[a-z]/u.test(value) && /[A-Z]/u.test(value) && /[0-9]/u.test(value);
}
