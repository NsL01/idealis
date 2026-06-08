from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    collaborator_ids = fields.One2many(
        'account.move.collaborator',
        'move_id',
        string='Collaborators',
    )

    @api.constrains('state', 'collaborator_ids')
    def _check_collaborative_amounts(self):
        for move in self:
            if move.state == 'posted' and move.move_type in ('out_invoice', 'out_refund') and move.collaborator_ids:
                total_share = sum(move.collaborator_ids.mapped('amount'))
                if move.currency_id.compare_amounts(total_share, move.amount_total) != 0:
                    symbol = move.currency_id.symbol or ''
                    raise ValidationError(_(
                        "The sum of the assigned amounts (%(total_share).2f %(symbol)s) must equal the invoice total (%(amount_total).2f %(symbol)s)."
                    ) % {
                        'total_share': total_share,
                        'amount_total': move.amount_total,
                        'symbol': symbol,
                    })
