from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError


class AccountMoveCollaborator(models.Model):
    _name = 'account.move.collaborator'
    _description = 'Collaborative Invoice Contributor'
    _order = 'id'
    _rec_name = 'contributor_id'

    move_id = fields.Many2one('account.move', string='Invoice')
    contributor_id = fields.Many2one('res.partner', required=True)
    amount = fields.Monetary(currency_field='currency_id', required=True)
    percentage = fields.Float(compute='_compute_percentage', inverse='_inverse_percentage', store=True)
    currency_id = fields.Many2one(related='move_id.currency_id', store=True) # we store it to ease the compute load on finalized moves
    amount_paid = fields.Monetary(compute='_compute_payment_amount', currency_field='currency_id', store=True)
    amount_remaining = fields.Monetary(compute='_compute_payment_amount', currency_field='currency_id', store=True)
    status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid')
    ], compute='_compute_payment_status', store=True, default='unpaid')

    @api.depends('contributor_id.name', 'amount', 'currency_id.symbol')
    def _compute_display_name(self):
        for col in self:
            partner_name = col.contributor_id.name or _("Unknown")
            currency_symbol = col.currency_id.symbol or ""
            col.display_name = f"{partner_name} ({col.amount_remaining} {currency_symbol})".strip()

    @api.depends('amount', 'move_id.amount_total')
    def _compute_percentage(self):
        for col in self:
            col.percentage = col.amount / col.move_id.amount_total if col.move_id.amount_total else 0

    def _inverse_percentage(self):
        for col in self:
            if col.move_id.amount_total:
                amount = col.percentage * col.move_id.amount_total
                col.amount = col.move_id.currency_id.round(amount) if col.move_id.currency_id else amount

    @api.depends(
        'amount',
        'move_id.line_ids.matched_debit_ids.debit_amount_currency',
        'move_id.line_ids.matched_debit_ids.credit_amount_currency',
        'move_id.line_ids.matched_credit_ids.debit_amount_currency',
        'move_id.line_ids.matched_credit_ids.credit_amount_currency',
    )
    def _compute_payment_amount(self):
        """
        Compute the amount paid and remaining for each collaborator.
        We base our computation on the debit and credit amount of the receivable lines of the move.
        """
        for col in self:
            col.amount_paid = 0
            col.amount_remaining = col.amount
            if col.move_id and col.contributor_id:
                receivable_lines = col.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')

                all_credit_lines = receivable_lines.matched_credit_ids
                all_debit_lines = receivable_lines.matched_debit_ids

                # get all money paid for this collaborator
                total_paid = sum(all_credit_lines.filtered_domain([('credit_move_id.partner_id', '=', col.contributor_id.id)]).mapped('debit_amount_currency'))
                total_paid += sum(all_debit_lines.filtered_domain([('debit_move_id.partner_id', '=', col.contributor_id.id)]).mapped('credit_amount_currency')) 

                col.amount_paid = total_paid
                remaining = col.amount - total_paid
                col.amount_remaining = col.currency_id.round(remaining) if col.currency_id else remaining

    @api.depends('amount_paid', 'amount_remaining')
    def _compute_payment_status(self):
        for col in self:
            if col.amount_remaining <= 0:
                col.status = 'paid'
            elif col.amount_paid > 0:
                col.status = 'partial'
            else:
                col.status = 'unpaid'

    def action_send_reminder(self):
        for col in self:
            if not col.contributor_id.email:
                raise UserError(_("The contributor %s does not have a configured email address.") % col.contributor_id.name)
            if col.status == 'paid':
                raise UserError(_("The contributor %s has already paid.") % col.contributor_id.name)

            body_html = _(
                "<p>Dear %s,</p>"
                "<p>This is a reminder to pay your share of invoice %s.</p>"
                "<p>Remaining Amount: <strong>%s %s</strong></p>"
            ) % (
                col.contributor_id.name,
                col.move_id.name or '',
                col.amount_remaining,
                col.currency_id.symbol or ''
            )
            mail_values = {
                'subject': _("Payment Reminder: Invoice %s") % (col.move_id.name or ''),
                'email_to': col.contributor_id.email,
                'body_html': body_html,
                'recipient_ids': [Command.link(col.contributor_id.id)],
            }
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
