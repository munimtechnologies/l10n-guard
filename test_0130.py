#!/usr/bin/env python3
"""l10n-guard 0.13.0: antonym-collision without the upload/download word
class, as fixed in advance by the census's antonym-collision/HOLDOUT2-PREREG.md
(H3 held: antonym-collision/HOLDOUT2-RESULTS.md). The rows are the 42 real
warnings that v0.12.0 raised in that test (Jellyfin Web ee8efb41, Uptime Kuma
b092505f, Rocket.Chat ad2047e7, Bitwarden 9e54ce7b), each checked on its own
two-key catalog; keys are shortened to "a" and "b". Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g

# (project, locale, English a, English b, shared value): the 36 warnings
# outside the upload/download class. 0.13.0 must still flag each one.
KEPT = [
    ("bitwarden-web", "ar", "Confirm vault export", "Confirm vault import", "تأكيد تصدير الخزانة"),
    ("bitwarden-web", "ar", "Data successfully exported", "Data successfully imported", "تم استيراد البيانات بنجاح"),
    ("bitwarden-web", "ja", "Confirm vault export", "Confirm vault import", "保管庫のエクスポートの確認"),
    ("bitwarden-web", "pt_PT", "Require admin approval for invite link is enabled",
     "Require admin approval for invite link is disabled",
     "A exigência de aprovação do administrador para o link de convite está desativada"),
    ("jellyfin-web", "eo", "SpeedToSync maximum delay", "SpeedToSync minimum delay", "Minimuma prokrasto de SpeedToSync"),
    ("jellyfin-web", "ro", "Airs after season", "Airs before season", "Emis după sezonul"),
    ("rocket-chat", "af", "User is blocked", "User is unblocked", "Gebruiker is geblokkeer"),
    ("rocket-chat", "az", "Custom script for logged in users", "Custom script for logged out users",
     "Daxil olanlar üçün xüsusi skript"),
    ("rocket-chat", "az", "Room archived", "Room unarchived", "Otaq arxivləşdirildi"),
    ("rocket-chat", "bg", "Mute user", "Unmute user", "Заглушаване на потребителя"),
    ("rocket-chat", "bg", "Unmute user", "Mute user", "Заглушаване на потребителя"),
    ("rocket-chat", "cs", "Room archived", "Room unarchived", "Skrýt zprávy „Místnost archivována“"),
    ("rocket-chat", "da", "Room has been archived", "Room has been unarchived", "Værelset er blevet arkiveret"),
    ("rocket-chat", "da", "User is blocked", "User is unblocked", "Brugeren er blokeret"),
    ("rocket-chat", "el", "This room has been archived by {{username}}", "This room has been unarchived by {{username}}",
     "Αυτό το δωμάτιο έχει αρχειοθετηθεί από το χρήστη {{username}}"),
    ("rocket-chat", "id", "Channel with name `#{{channelName}}` has been archived successfully",
     "Channel with name `#{{channelName}}` has been unarchived successfully",
     "Channel dengan nama `#{{channelName}}` telah diarsipkan berhasil"),
    ("rocket-chat", "id", "Room archived", "Room unarchived", "kamar diarsipkan"),
    ("rocket-chat", "id", "Room has been archived", "Room has been unarchived", "Kamar telah diarsipkan"),
    ("rocket-chat", "id", "This room has been archived by {{username}}", "This room has been unarchived by {{username}}",
     "Ruangan ini telah diarsipkan oleh {{username}}"),
    ("rocket-chat", "ka-GE", "Add custom OAuth", "Remove custom OAuth", "დაამატეთ პირადი oauth"),
    ("rocket-chat", "km", "Room archived", "Room unarchived",
     "បន្ទប់ទុក​​ក្នុងប័ណ្ណសារ"),
    ("rocket-chat", "km", "User is blocked", "User is unblocked", "អ្នកប្រើត្រូវបានទប់ស្កាត់"),
    ("rocket-chat", "ku", "Max length is {{limit}}", "Min length is {{limit}}", "Mezinahiya {{limit}} e"),
    ("rocket-chat", "ku", "Add user", "Remove user", "Bikarhêner hilbijêre"),
    ("rocket-chat", "mn", "Offline users", "Online users", "Онлайн хэрэглэгчид"),
    ("rocket-chat", "ms-MY", "User is blocked", "User is unblocked", "Pengguna disekat"),
    ("rocket-chat", "nn", "Room has been archived", "Room has been unarchived", "Rom har blitt arkivert"),
    ("rocket-chat", "nn", "Unmute user", "Mute user", "Slå av brukeren"),
    ("rocket-chat", "th-TH", "Room archived", "Room unarchived", "ห้องเก็บถาวร"),
    ("rocket-chat", "th-TH", "Room archived", "Room unarchived", "ห้องเก็บถาวร"),
    ("rocket-chat", "uk", "Yes, archive it!", "Yes, unarchive it!", "Так, архівуйте це!"),
    ("rocket-chat", "vi-VN", "Custom script for logged in users", "Custom script for logged out users",
     "Tập lệnh Tuỳ chỉnh cho Người dùng đăng nhập"),
    ("rocket-chat", "zh-HK", "This room has been archived by {{username}}", "This room has been unarchived by {{username}}",
     "这个房间已被{{username}}存档"),
    ("uptime-kuma", "bar", "Are you sure you want to disable 2FA?", "Are you sure you want to enable 2FA?",
     "Bist da sicher, dass d'2FA wirklich ausschoidn wuist?"),
    ("uptime-kuma", "sr", "Export Backup", "Import Backup", "Извези резервну копију"),
    ("uptime-kuma", "ur", "Export Backup", "Import Backup", "بیک اپ درآمد کریں"),
]

# The 6 upload/download warnings. 0.13.0 must flag none of them. The
# Hungarian row was graded a real defect; dropping the class loses it.
DROPPED = [
    ("bitwarden-web", "hu", "Download license", "Upload license", "Licensz letöltése"),
    ("bitwarden-web", "ru", "Download license", "Upload license", "Загрузить лицензию"),
    ("jellyfin-web", "ru", "Download", "Upload", "Загрузить"),
    ("jellyfin-web", "uk", "Download", "Upload", "Завантажити"),
    ("rocket-chat", "fi", "Download", "Upload", "Lataa"),
    ("rocket-chat", "fi", "Download", "Upload", "Lataa"),
]


def collisions(source, target):
    return [(p["key"], p.get("other_key")) for p in g.check_catalog(source, target)
            if p["code"] == "antonym-collision"]


class AntonymCollision0130Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 13, 0))

    def test_upload_class_dropped(self):
        self.assertNotIn("UPLOAD", g._ANTONYM_CLASSES)
        for word in ("upload", "uploaded", "download", "downloaded"):
            self.assertNotIn(word, g._ANTONYMS)
        self.assertEqual(len(g._ANTONYM_CLASSES), 39)

    def test_other_classes_kept(self):
        for word, cls in (("archive", "ARCHIVE"), ("unblock", "BLOCK"), ("export", "IMPORT"),
                          ("mute", "MUTE"), ("min", "MAX"), ("after", "BEFORE")):
            self.assertEqual(g._ANTONYMS[word][0], cls)

    def test_upload_not_a_pair(self):
        # Shaped like the first test's Lobe Chat rows; written for the test.
        self.assertEqual(g.antonym_pairs({"a": "Download failed", "b": "Upload failed"}), [])
        self.assertEqual(g.antonym_pairs({"a": "Upload and lock", "b": "Upload and unlock"}), [("a", "b")])
        self.assertEqual(g.antonym_pairs({"a": "Upload and lock", "b": "Download and unlock"}), [])

    def test_holdout2_kept(self):
        self.assertEqual(len(KEPT), 36)
        for project, locale, en1, en2, value in KEPT:
            with self.subTest(project=project, locale=locale, en=en1):
                self.assertEqual(collisions({"a": en1, "b": en2}, {"a": value, "b": value}), [("a", "b")])

    def test_holdout2_dropped(self):
        self.assertEqual(len(DROPPED), 6)
        for project, locale, en1, en2, value in DROPPED:
            with self.subTest(project=project, locale=locale, en=en1):
                self.assertEqual(collisions({"a": en1, "b": en2}, {"a": value, "b": value}), [])

    def test_nested_keys(self):
        # Bitwarden messages.json shape: {"key": {"message": ...}}.
        en = {"confirmVaultExport": {"message": "Confirm vault export"},
              "confirmVaultImport": {"message": "Confirm vault import"}}
        ja = {"confirmVaultExport": {"message": "保管庫のエクスポートの確認"},
              "confirmVaultImport": {"message": "保管庫のエクスポートの確認"}}
        self.assertEqual(collisions(en, ja), [("confirmVaultExport.message", "confirmVaultImport.message")])


if __name__ == "__main__":
    unittest.main()
