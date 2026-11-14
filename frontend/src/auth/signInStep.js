// Interpret the SDK response without starting a second authentication session.
export function signInStep(result) {
  const next = result.nextStep || {};
  if (result.isSignedIn || next.signInStep === "DONE") return { flow: "done" };
  const challenge = next.signInStep;
  switch (challenge) {
    case "CONFIRM_SIGN_UP": return { flow: "confirmSignUp" };
    case "RESET_PASSWORD": return { flow: "forgot" };
    case "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED":
      if (next.missingAttributes?.length) return { flow: "unsupported" };
      return { flow: "newPassword" };
    case "CONTINUE_SIGN_IN_WITH_EMAIL_SETUP": return { flow: "emailSetup" };
    case "CONTINUE_SIGN_IN_WITH_TOTP_SETUP":
      return next.totpSetupDetails?.sharedSecret
        ? { flow: "totpSetup", secret: next.totpSetupDetails.sharedSecret }
        : { flow: "unsupported" };
    case "CONTINUE_SIGN_IN_WITH_MFA_SELECTION":
    case "CONTINUE_SIGN_IN_WITH_MFA_SETUP_SELECTION": {
      const methods = [...new Set(next.allowedMFATypes || [])].filter(x => ["SMS", "EMAIL", "TOTP"].includes(x));
      return methods.length ? { flow: "mfa", challenge, methods } : { flow: "unsupported" };
    }
    case "CONFIRM_SIGN_IN_WITH_SMS_CODE":
    case "CONFIRM_SIGN_IN_WITH_EMAIL_CODE":
    case "CONFIRM_SIGN_IN_WITH_TOTP_CODE": return { flow: "mfa", challenge, methods: [] };
    default: return { flow: "unsupported" };
  }
}
