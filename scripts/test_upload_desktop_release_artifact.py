import os
import unittest
from unittest.mock import patch

from scripts.upload_desktop_release_artifact import artifact_upload_data


BASE_ENV = {
    "RELEASE_CALLBACK_TOKEN": "test-token",
    "RELEASE_ID": "47",
    "RELEASE_VERSION": "2.0.28-beta.1",
    "RELEASE_CHANNEL": "beta",
    "BUILD_RUN_ID": "github:36412592049",
    "GITHUB_RUN_ID": "36412592049",
    "RELEASE_ARTIFACT_VERIFICATION_STATUS": "verified",
    "RELEASE_ARTIFACT_VERIFICATION_RUN_ID": "github:36412592049",
}


class ArtifactUploadDataTests(unittest.TestCase):
    def test_verified_macos_upload_binds_verification_to_build_run(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            data = artifact_upload_data("mac-arm64", "uploaded")
        self.assertEqual(data["verificationStatus"], "verified")
        self.assertEqual(data["buildRunId"], "github:36412592049")
        self.assertEqual(data["verificationRunId"], data["buildRunId"])
        self.assertNotIn("smokeStatus", data)

    def test_verified_windows_upload_preserves_install_and_signature_results(self):
        environment = {
            **BASE_ENV,
            "RELEASE_ARTIFACT_SIGNATURE_STATUS": "unsigned",
            "RELEASE_ARTIFACT_SMOKE_STATUS": "passed",
        }
        with patch.dict(os.environ, environment, clear=True):
            data = artifact_upload_data("win-x64", "uploaded")
        self.assertEqual(data["signatureStatus"], "unsigned")
        self.assertEqual(data["smokeStatus"], "passed")

    def test_unverified_or_unbound_upload_is_rejected(self):
        invalid = [
            {"RELEASE_ARTIFACT_VERIFICATION_STATUS": ""},
            {"RELEASE_ARTIFACT_VERIFICATION_STATUS": "unverified"},
            {"RELEASE_ARTIFACT_VERIFICATION_RUN_ID": ""},
            {"RELEASE_ARTIFACT_VERIFICATION_RUN_ID": "github:other"},
            {"BUILD_RUN_ID": "github:other"},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides), patch.dict(os.environ, {**BASE_ENV, **overrides}, clear=True):
                with self.assertRaises(RuntimeError):
                    artifact_upload_data("mac-x64", "uploaded")

    def test_windows_upload_requires_install_and_signature_results(self):
        invalid = [
            {},
            {"RELEASE_ARTIFACT_SIGNATURE_STATUS": "invalid", "RELEASE_ARTIFACT_SMOKE_STATUS": "passed"},
            {"RELEASE_ARTIFACT_SIGNATURE_STATUS": "valid", "RELEASE_ARTIFACT_SMOKE_STATUS": "failed"},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides), patch.dict(os.environ, {**BASE_ENV, **overrides}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "signature and installation smoke"):
                    artifact_upload_data("win-x64", "uploaded")

    def test_only_uploaded_artifacts_use_the_upload_callback(self):
        with patch.dict(os.environ, BASE_ENV, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be uploaded"):
                artifact_upload_data("mac-arm64", "succeeded")


if __name__ == "__main__":
    unittest.main()
