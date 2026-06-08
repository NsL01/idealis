from odoo import api, models


class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    @api.model_create_multi
    def create(self, vals_list):
        """
        We update amount_paid and status for each collaborator when a partial reconcile is created
        """
        partials = super().create(vals_list)
        moves = (partials.debit_move_id.move_id | partials.credit_move_id.move_id).filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund') # we keep only customer invoices & refunds
        )
        if moves:
            collaborators = self.env['account.move.collaborator'].search([('move_id', 'in', moves.ids)])
            if collaborators:
                collaborators.modified(['amount_paid', 'amount_remaining', 'status'])
        return partials

    def unlink(self):
        """
        We update amount_paid and status for each collaborator when a partial reconcile is deleted
        """
        moves = (self.debit_move_id.move_id | self.credit_move_id.move_id).filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund') # we keep only customer invoices & refunds
        )
        res = super().unlink()
        if moves:
            collaborators = self.env['account.move.collaborator'].search([('move_id', 'in', moves.ids)])
            if collaborators:
                collaborators.modified(['amount_paid', 'amount_remaining', 'status'])
        return res
