from odoo import fields, models


class RequestStage(models.Model):
    _inherit = "request.stage"

    hr_leave_type_ids = fields.Many2many("hr.leave.type", string="Types ", copy=False)
