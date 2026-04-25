import json
import unittest
from unittest.mock import MagicMock, patch

from services import gdrive_service


class GoogleDriveCredentialSelectionTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict("os.environ", {}, clear=True)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        self.config_patches = [
            patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_JSON", ""),
            patch.object(gdrive_service.config, "GOOGLE_OAUTH_TOKEN_JSON", ""),
            patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_FILE", "missing-credentials.json"),
        ]
        for config_patch in self.config_patches:
            config_patch.start()
            self.addCleanup(config_patch.stop)

        self.path_patcher = patch.object(gdrive_service.Path, "is_file", return_value=False)
        self.path_patcher.start()
        self.addCleanup(self.path_patcher.stop)

    @patch.object(gdrive_service.service_account.Credentials, "from_service_account_info")
    @patch.object(gdrive_service.OAuthCredentials, "from_authorized_user_info")
    def test_service_account_wins_when_both_are_set(self, oauth_factory, service_factory):
        service_creds = MagicMock(name="service_creds")
        service_factory.return_value = service_creds
        oauth_factory.return_value = MagicMock(name="oauth_creds")

        with patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_JSON", json.dumps({"type": "service_account"})), \
             patch.object(gdrive_service.config, "GOOGLE_OAUTH_TOKEN_JSON", json.dumps({
                 "refresh_token": "refresh",
                 "client_id": "client",
                 "client_secret": "secret",
                 "token_uri": "https://oauth2.googleapis.com/token",
             })):
            creds, auth_type = gdrive_service._get_drive_credentials()

        self.assertIs(creds, service_creds)
        self.assertEqual(auth_type, "service_account")
        oauth_factory.assert_not_called()

    @patch.object(gdrive_service.service_account.Credentials, "from_service_account_info")
    def test_service_account_used_when_oauth_is_empty(self, service_factory):
        service_creds = MagicMock(name="service_creds")
        service_factory.return_value = service_creds

        with patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_JSON", json.dumps({"type": "service_account"})), \
             patch.object(gdrive_service.config, "GOOGLE_OAUTH_TOKEN_JSON", ""):
            creds, auth_type = gdrive_service._get_drive_credentials()

        self.assertIs(creds, service_creds)
        self.assertEqual(auth_type, "service_account")

    @patch.object(gdrive_service.service_account.Credentials, "from_service_account_info")
    @patch.object(gdrive_service.OAuthCredentials, "from_authorized_user_info")
    def test_oauth_used_when_service_account_is_missing(self, oauth_factory, service_factory):
        oauth_creds = MagicMock(name="oauth_creds")
        oauth_creds.has_scopes.return_value = True
        oauth_creds.valid = True
        oauth_factory.return_value = oauth_creds

        token_json = json.dumps({
            "refresh_token": "refresh",
            "client_id": "client",
            "client_secret": "secret",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": gdrive_service.SCOPES,
        })
        with patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_JSON", ""), \
             patch.object(gdrive_service.config, "GOOGLE_OAUTH_TOKEN_JSON", token_json):
            creds, auth_type = gdrive_service._get_drive_credentials()

        self.assertIs(creds, oauth_creds)
        self.assertEqual(auth_type, "oauth")
        service_factory.assert_not_called()

    def test_missing_all_credentials_raises_clear_error(self):
        with patch.object(gdrive_service.config, "GOOGLE_CREDENTIALS_JSON", ""), \
             patch.object(gdrive_service.config, "GOOGLE_OAUTH_TOKEN_JSON", ""):
            with self.assertRaisesRegex(RuntimeError, "Google Drive 未設定"):
                gdrive_service._get_drive_credentials()


if __name__ == "__main__":
    unittest.main()
