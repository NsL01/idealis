from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo import Command


@tagged('post_install', '-at_install')
class TestCollaborativeInvoice(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_alice = cls.env['res.partner'].create({'name': 'Alice'})
        cls.partner_bob = cls.env['res.partner'].create({'name': 'Bob'})
        cls.partner_charlie = cls.env['res.partner'].create({'name': 'Charlie'})

    def test_collaborative_exact_split(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-06-08',
            'invoice_line_ids': [
                Command.create({'name': 'Services', 'price_unit': 1200}),
            ],
        })
        
        self.env['account.move.collaborator'].create([
            {'move_id': invoice.id, 'contributor_id': self.partner_alice.id, 'amount': 500},
            {'move_id': invoice.id, 'contributor_id': self.partner_bob.id, 'amount': 400},
            {'move_id': invoice.id, 'contributor_id': self.partner_charlie.id, 'amount': 300},
        ])
        
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')

    def test_collaborative_invalid_split(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-06-08',
            'invoice_line_ids': [
                Command.create({'name': 'Services', 'price_unit': 1200}),
            ],
        })
        
        self.env['account.move.collaborator'].create([
            {'move_id': invoice.id, 'contributor_id': self.partner_alice.id, 'amount': 500},
            {'move_id': invoice.id, 'contributor_id': self.partner_bob.id, 'amount': 400},
        ])
        
        # Try to post. It should raise a ValidationError.
        with self.assertRaises(ValidationError):
            invoice.action_post()

    def test_collaborative_payment_matching(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-06-08',
            'invoice_line_ids': [
                Command.create({'name': 'Services', 'price_unit': 1200}),
            ],
        })
        
        col_alice = self.env['account.move.collaborator'].create({'move_id': invoice.id, 'contributor_id': self.partner_alice.id, 'amount': 500})
        col_bob = self.env['account.move.collaborator'].create({'move_id': invoice.id, 'contributor_id': self.partner_bob.id, 'amount': 400})
        col_charlie = self.env['account.move.collaborator'].create({'move_id': invoice.id, 'contributor_id': self.partner_charlie.id, 'amount': 300})
        
        invoice.action_post()
        
        # Register a payment from Alice of 500
        register_wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'payment_date': '2026-06-08',
            'amount': 500,
            'collaborator_id': col_alice.id,
            'journal_id': self.company_data['default_journal_bank'].id,
        })
        register_wizard._create_payments()
        
        # Check collaborator status for Alice
        col_alice.invalidate_recordset()
        self.assertEqual(col_alice.amount_paid, 500)
        self.assertEqual(col_alice.amount_remaining, 0)
        self.assertEqual(col_alice.status, 'paid')
        
        # Bob paid 200 (partial payment)
        register_wizard_bob = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'payment_date': '2026-06-08',
            'amount': 200,
            'collaborator_id': col_bob.id,
            'journal_id': self.company_data['default_journal_bank'].id,
        })
        register_wizard_bob._create_payments()
        
        col_bob.invalidate_recordset()
        self.assertEqual(col_bob.amount_paid, 200)
        self.assertEqual(col_bob.amount_remaining, 200)
        self.assertEqual(col_bob.status, 'partial')
        
        # Charlie has not paid
        col_charlie.invalidate_recordset()
        self.assertEqual(col_charlie.amount_paid, 0)
        self.assertEqual(col_charlie.amount_remaining, 300)
        self.assertEqual(col_charlie.status, 'unpaid')

    def test_collaborative_send_reminder(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-06-08',
            'invoice_line_ids': [
                Command.create({'name': 'Services', 'price_unit': 1200}),
            ],
        })

        # Partner with email
        self.partner_alice.email = 'alice@example.com'
        col_alice = self.env['account.move.collaborator'].create({'move_id': invoice.id, 'contributor_id': self.partner_alice.id, 'amount': 600})

        # Partner without email
        self.partner_bob.email = False
        col_bob = self.env['account.move.collaborator'].create({'move_id': invoice.id, 'contributor_id': self.partner_bob.id, 'amount': 600})

        # Try to send reminder to partner without email - should raise UserError
        from odoo.exceptions import UserError
        with self.assertRaises(UserError) as cm:
            col_bob.action_send_reminder()
        self.assertIn("does not have a configured email address", str(cm.exception))

        # Try to send reminder to Alice (unpaid, has email) - should succeed
        col_alice.action_send_reminder()

        # Check mail.mail was created and sent
        mail = self.env['mail.mail'].search([('email_to', '=', 'alice@example.com')], order='id desc', limit=1)
        self.assertTrue(mail, "Mail was not created")
        self.assertIn("Alice", mail.body_html)
        self.assertIn("reminder", mail.body_html.lower())

        # Pay Alice completely
        invoice.action_post()
        register_wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids
        ).create({
            'payment_date': '2026-06-08',
            'amount': 600,
            'collaborator_id': col_alice.id,
            'journal_id': self.company_data['default_journal_bank'].id,
        })
        register_wizard._create_payments()
        col_alice.invalidate_recordset()
        self.assertEqual(col_alice.status, 'paid')

        # Try to send reminder to Alice when status is 'paid' - should raise UserError
        with self.assertRaises(UserError) as cm:
            col_alice.action_send_reminder()
        self.assertIn("has already paid", str(cm.exception))
