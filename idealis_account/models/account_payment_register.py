from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    move_ids = fields.Many2many(
        'account.move',
        compute='_compute_move_ids',
        string="Invoices"
    )

    collaborator_id = fields.Many2one(
        'account.move.collaborator',
        string="Contributor",
        domain="[('move_id', 'in', move_ids)]"
    )

    @api.depends('line_ids')
    def _compute_move_ids(self):
        for wizard in self:
            wizard.move_ids = wizard.line_ids.move_id

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.collaborator_id:
            payment_vals['partner_id'] = self.collaborator_id.contributor_id.id
        return payment_vals
