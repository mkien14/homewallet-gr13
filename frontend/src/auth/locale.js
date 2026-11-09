import { CognitoIdentityProviderClient, GetUserCommand, UpdateUserAttributesCommand } from "@aws-sdk/client-cognito-identity-provider";
import { getAccessToken } from "./auth";
import { isReactAuthSession, readReactPreferredLocale, writeReactPreferredLocale } from "./cognito";
import { config } from "../config";

const region = config.userPoolId?.split("_")[0];
let client;

function cognitoClient() {
  if (!region) throw new Error("Cognito User Pool is not configured");
  client ||= new CognitoIdentityProviderClient({ region });
  return client;
}

async function pkceToken() {
  const token = await getAccessToken();
  if (!token) throw new Error("Cognito session is missing");
  return token;
}

export async function readCognitoPreferredLocale() {
  if (isReactAuthSession()) return readReactPreferredLocale();
  const result = await cognitoClient().send(new GetUserCommand({ AccessToken: await pkceToken() }));
  return result.UserAttributes?.find(({ Name }) => Name === "custom:preferred_locale")?.Value;
}

export async function writeCognitoPreferredLocale(locale) {
  const value = locale === "en" ? "en" : "vi";
  if (isReactAuthSession()) return writeReactPreferredLocale(value);
  await cognitoClient().send(new UpdateUserAttributesCommand({
    AccessToken: await pkceToken(),
    UserAttributes: [{ Name: "custom:preferred_locale", Value: value }],
  }));
}
