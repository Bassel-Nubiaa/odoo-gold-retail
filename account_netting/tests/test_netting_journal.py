"""Tests for the company netting journal."""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNettingJournal(TransactionCase):
    """The netting journal is a Miscellaneous journal set per company."""

    @classmethod
    def setUpClass(cls):
        """Create one Miscellaneous journal and one Sales journal."""
        super().setUpClass()
        cls.company = cls.env.company
        Journal = cls.env["account.journal"]
        cls.misc_journal = Journal.create({"name": "Netting", "code": "TNET", "type": "general"})
        cls.sale_journal = Journal.create({"name": "Test Sales", "code": "TSAL", "type": "sale"})

    def test_miscellaneous_journal_accepted(self):
        """A Miscellaneous journal can be the netting journal."""
        self.company.netting_journal_id = self.misc_journal
        self.assertEqual(self.company.netting_journal_id, self.misc_journal)

    def test_other_journal_type_refused(self):
        """A Sales journal cannot be the netting journal."""
        with self.assertRaises(ValidationError):
            self.company.netting_journal_id = self.sale_journal

    def test_setting_writes_company(self):
        """The Accounting setting saves the journal on the company."""
        settings = self.env["res.config.settings"].create({"netting_journal_id": self.misc_journal.id})
        settings.execute()
        self.assertEqual(self.company.netting_journal_id, self.misc_journal)