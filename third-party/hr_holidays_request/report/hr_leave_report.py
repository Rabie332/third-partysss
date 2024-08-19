from odoo import _, api, fields, models, tools
from odoo.osv import expression


class LeaveReport(models.Model):
    _inherit = "hr.leave.report"

    state = fields.Selection(
        selection_add=[("in_progress", "In progress"), ("done", "Done")]
    )

    # def init(self):
    #     tools.drop_view_if_exists(self._cr, "hr_leave_report")

    #     self._cr.execute(
    #         """
    #            CREATE or REPLACE view hr_leave_report as (
    #                SELECT row_number() over(ORDER BY leaves.employee_id) as id,
    #                leaves.employee_id as employee_id, leaves.name as name,
    #                leaves.number_of_days as number_of_days, leaves.leave_type as leave_type,
    #                leaves.category_id as category_id, leaves.department_id as department_id,
    #                leaves.holiday_status_id as holiday_status_id, leaves.state as state,
    #                leaves.holiday_type as holiday_type, leaves.date_from as date_from,
    #                leaves.date_to as date_to, leaves.payslip_status as payslip_status
    #                from (select
    #                    allocation.employee_id as employee_id,
    #                    allocation.private_name as name,
    #                    allocation.number_of_days as number_of_days,
    #                    allocation.category_id as category_id,
    #                    allocation.department_id as department_id,
    #                    allocation.holiday_status_id as holiday_status_id,
    #                    allocation.state as state,
    #                    allocation.holiday_type,
    #                    null as date_from,
    #                    null as date_to,
    #                    FALSE as payslip_status,
    #                    'allocation' as leave_type
    #                from hr_leave_allocation as allocation where allocation.active = 't'
    #                union all select
    #                    request.employee_id as employee_id,
    #                    request.private_name as name,
    #                    (request.number_of_days * -1) as number_of_days,
    #                    request.category_id as category_id,
    #                    request.department_id as department_id,
    #                    request.holiday_status_id as holiday_status_id,
    #                    request.state as state,
    #                    request.holiday_type,
    #                    request.date_from as date_from,
    #                    request.date_to as date_to,
              
    #                    'request' as leave_type
    #                from hr_leave as request) leaves
    #            );
    #        """
    #     )

    @api.model
    def action_time_off_analysis(self):
        domain = [("holiday_type", "=", "employee")]

        if self.env.context.get("active_ids"):
            domain = expression.AND(
                [
                    domain,
                    [
                        ("employee_id", "in", self.env.context.get("active_ids", [])),
                        ("state", "!=", "cancel"),
                    ],
                ]
            )

        return {
            "name": _("Time Off Analysis"),
            "type": "ir.actions.act_window",
            "res_model": "hr.leave.report",
            "view_mode": "tree,form,pivot",
            "search_view_id": self.env.ref(
                "hr_holidays.view_hr_holidays_filter_report"
            ).id,
            "domain": domain,
            "context": {"search_default_group_type": True, "search_default_year": True},
        }
