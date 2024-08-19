import logging
from datetime import datetime, time

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _

# from odoo.addons.resource.models.resource import HOURS_PER_DAY

_logger = logging.getLogger(__name__)


class HolidaysAllocation(models.Model):
    _name = "hr.leave.allocation"
    _inherit = ["request", "hr.leave.allocation"]

    def _default_employee(self):
        return self.env.context.get("default_employee_id") or self.env.user.employee_id

    state = fields.Selection(
        selection_add=[
            ("confirm", "To Approve"),
            ("refuse", "Refused"),
            ("validate1", "Second Approval"),
            ("validate", "Approved"),
        ],
        tracking=False,
    )
    remaining_leaves = fields.Float(
        compute="_compute_leaves", string="Remaining Time Off"
    )
    last_number_of_days = fields.Float("Solde of last year")
    date_last_number_of_days = fields.Date("Date update solde of last year")
    active = fields.Boolean("Active", default=True)
    holiday_status_id = fields.Many2one(
        readonly=True, states={"draft": [("readonly", False)]}
    )
    # interval_unit = fields.Selection(
        
    #     readonly=True, states={"draft": [("readonly", False)]}
    # )
    
    
    interval_unit = fields.Selection([
    ('day', 'Day'),
    ('week', 'Week'),
    ('month', 'Month'),
    ('year', 'Year')
], readonly=True, states={"draft": [("readonly", False)]})


    number_per_interval = fields.Float(
        readonly=True, states={"draft": [("readonly", False)]}
    )
    interval_number = fields.Integer(
        readonly=True, states={"draft": [("readonly", False)]}
    )
    # unit_per_interval = fields.Selection(
    #     readonly=True, states={"draft": [("readonly", False)]}
    # )
    
    unit_per_interval = fields.Selection([
    ('hours', 'Hours'),
    ('days', 'Days'),
    ('weeks', 'Weeks')
], string="Unit per Interval", readonly=True, states={"draft": [("readonly", False)]})


    mode_company_id = fields.Many2one(
        readonly=True, states={"draft": [("readonly", False)]}
    )
    refuse_reason = fields.Char(string="Refusal reason")

    # ------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------

    @api.depends("stage_id")
    def _compute_display_button(self):
        for allocation in self:
            users = allocation._get_approvers()
            allocation.display_button_refuse = False
            allocation.display_button_accept = False
            allocation.display_button_send = False
            if allocation.state == "draft" and (
                (
                    allocation.create_uid
                    and allocation.create_uid.id == allocation.env.uid
                )
                or allocation.env.user.has_group("hr.group_hr_manager")
            ):
                allocation.display_button_send = True

            elif allocation.state == "in_progress" and (
                allocation.env.uid in users
                or allocation.env.user.has_group("hr.group_hr_manager")
            ):
                allocation.display_button_accept = True
                allocation.display_button_refuse = True

    @api.depends("employee_id", "holiday_status_id")
    def _compute_leaves(self):
        for allocation in self:
            super(HolidaysAllocation, allocation)._compute_leaves()
            leave_type = allocation.holiday_status_id.with_context(
                employee_id=allocation.employee_id.id
            )
            allocation.remaining_leaves = leave_type.remaining_leaves

    # ------------------------------------------------------------
    # Constraint methods
    # ------------------------------------------------------------
    @api.constrains("holiday_status_id", "employee_id")
    def _check_employee_holiday_status(self):
        """Check holiday type."""
        if self.search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("employee_id", "!=", False),
                ("holiday_status_id", "=", self.holiday_status_id.id),
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
            ]
        ):
            raise ValidationError(
                _("The employee %s has allocation for holiday type %s")
                % (self.employee_id.name, self.holiday_status_id.name)
            )

    @api.constrains("number_of_days")
    def _check_number_of_days(self):
        if (
            self.allocation_type == "regular"
            and self.number_of_days > self.holiday_status_id.maximum_days
            and self.holiday_status_id.maximum_days > 0
        ):
            raise ValidationError(
                _("Number of days should be less than maximum days of holidays type")
            )

    @api.model
    def _update_last_year_stock(self):
        """Method called by the cron task in order
        to increment the number_of_days when necessary."""
        today = fields.Date.from_string(fields.Date.today())
        domain = [
            ("allocation_type", "=", "accrual"),
            ("employee_id.active", "=", True),
            ("state", "=", "done"),
            ("holiday_type", "=", "employee"),
            "|",
            ("date_to", "=", False),
            ("date_to", ">", fields.Datetime.now()),
            ("employee_id", "!=", False),
        ]
        holidays = self.env["hr.leave.allocation"].search(domain)
        for holiday in holidays:
            if (
                holiday.last_number_of_days > 0
                and holiday.holiday_status_id.availability
                and (today - holiday.date_last_number_of_days).days
                == holiday.holiday_status_id.availability
            ):
                holiday.number_of_days = (
                    holiday.number_of_days - holiday.last_number_of_days
                )
                holiday.last_number_of_days = 0
            if (
                holiday.employee_id.date_direct_action
                and holiday.employee_id.date_direct_action < today
                and relativedelta(
                    datetime.now().date(), holiday.employee_id.date_direct_action
                ).months
                == 0
                and relativedelta(
                    datetime.now().date(), holiday.employee_id.date_direct_action
                ).days
                == 0
            ):
                taken_days = sum(
                    self.env["hr.leave"]
                    .with_context(active_test=False)
                    .search(
                        [
                            ("holiday_status_id", "=", holiday.holiday_status_id.id),
                            ("employee_id", "=", holiday.employee_id.id),
                            ("state", "=", "done"),
                        ]
                    )
                    .mapped("number_of_days")
                )
                holiday.last_number_of_days = holiday.number_of_days - taken_days
                holiday.date_last_number_of_days = today

    @api.model
    def _update_accrual(self):
        """
        Method called by the cron task in order to increment the number_of_days when
        necessary.
        """
        today = fields.Date.from_string(fields.Date.today())
        domain = [
            ("allocation_type", "=", "accrual"),
            ("employee_id.active", "=", True),
            ("state", "=", "done"),
            ("holiday_type", "=", "employee"),
            "|",
            ("date_to", "=", False),
            ("date_to", ">", fields.Datetime.now()),
            "|",
            ("nextcall", "=", False),
            ("nextcall", "<=", today),
        ]

        holidays = self.search(domain)
        for holiday in holidays:
            values = {}
            delta = relativedelta(days=0)
            if holiday.interval_unit == "days":
                delta = relativedelta(days=holiday.interval_number)
            if holiday.interval_unit == "weeks":
                delta = relativedelta(weeks=holiday.interval_number)
            if holiday.interval_unit == "months":
                delta = relativedelta(months=holiday.interval_number)
            if holiday.interval_unit == "years":
                delta = relativedelta(years=holiday.interval_number)
            # get next_call date
            date = (
                holiday.nextcall
                if holiday.nextcall
                else holiday.employee_id.date_direct_action
                or holiday.employee_id.create_date.date()
            )
            values["nextcall"] = holiday.get_nextcall(date)
            period_start = datetime.combine(today, time(0, 0, 0)) - delta
            period_end = datetime.combine(today, time(0, 0, 0))
            # We have to check when the employee has been created
            # in order to not allocate him/her too much leaves
            if isinstance(holiday.employee_id._get_date_start_work(), datetime):
                start_date = holiday.employee_id._get_date_start_work()
            else:
                start_date = datetime.combine(
                    holiday.employee_id._get_date_start_work(), time(0, 0, 0)
                )
            # If employee is created after the period, we cancel the computation
            if period_end <= start_date:
                holiday.write(values)
                continue

            # If employee created during the period,
            # taking the date at which he has been created
            if period_start <= start_date:
                period_start = start_date

            worked = holiday.employee_id._get_work_days_data(
                period_start,
                period_end,
                domain=[
                    ("holiday_id.holiday_status_id.unpaid", "=", True),
                    ("time_type", "=", "leave"),
                ],
            )["days"]
            left = holiday.employee_id._get_leave_days_data(
                period_start,
                period_end,
                domain=[
                    ("holiday_id.holiday_status_id.unpaid", "=", True),
                    ("time_type", "=", "leave"),
                ],
            )["days"]
            prorata = worked / (left + worked) if worked else 0

            days_to_give = holiday.number_per_interval
            if holiday.unit_per_interval == "hours":
                # As we encode everything in days in the database we need to convert
                # the number of hours into days for this we use the
                # mean number of hours set on the employee's calendar
                days_to_give = days_to_give / (
                    holiday.employee_id.resource_calendar_id.hours_per_day
                    or HOURS_PER_DAY
                )

            values["number_of_days"] = holiday.number_of_days + days_to_give * prorata
            if holiday.accrual_limit > 0:
                values["number_of_days"] = min(
                    values["number_of_days"], holiday.accrual_limit
                )

            holiday.write(values)

    ####################################################
    # ORM Overrides methods
    ####################################################

    def name_get(self):
        res = []
        for allocation in self:
            if allocation.holiday_type == "company":
                target = allocation.mode_company_id.name
            elif allocation.holiday_type == "department":
                target = allocation.department_id.name
            elif allocation.holiday_type == "category":
                target = allocation.category_id.name
            else:
                target = allocation.employee_id.sudo().name

            if allocation.type_request_unit == "hour":
                res.append(
                    (
                        allocation.id,
                        _("Allocation of %s : %.2f hour(s) to %s")
                        % (
                            allocation.holiday_status_id.sudo().name,
                            allocation.number_of_hours_display,
                            target,
                        ),
                    )
                )
            else:
                res.append(
                    (
                        allocation.id,
                        _("Allocation of %s : %.2f day(s) to %s")
                        % (
                            allocation.holiday_status_id.sudo().name,
                            allocation.number_of_days,
                            target,
                        ),
                    )
                )
        return res

    @api.model
    def fields_view_get(
        self, view_id=None, view_type="form", toolbar=False, submenu=False
    ):
        """fields_view_get to remove create and edit and delete
        from menu Allocations in self service."""
        res = super(HolidaysAllocation, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu
        )
        if self.env.context.get("no_display_create_edit"):
            doc = etree.XML(res["arch"])
            for node in doc.xpath("//tree"):
                node.set("create", "0")
                node.set("edit", "0")
                node.set("duplicate", "0")
            for node in doc.xpath("//form"):
                node.set("create", "0")
                node.set("edit", "0")
                node.set("duplicate", "0")
            res["arch"] = etree.tostring(doc, encoding="unicode")
        return res

    ####################################################
    # Business methods
    ####################################################

    def action_validate(self):
        for holiday in self:
            # Fixme: We have deleted UserError message
            #  and the original odoo validation workflow ...
            holiday._action_validate_create_childs()
        self.activity_update()
        return True

    def _action_validate_create_childs(self):
        childs = self.env["hr.leave.allocation"]
        if self.state == "done" and self.holiday_type in [
            "category",
            "department",
            "company",
        ]:
            if self.holiday_type == "category":
                employees = self.category_id.employee_ids
            elif self.holiday_type == "department":
                employees = self.department_id.member_ids
            else:
                employees = (
                    self.env["hr.employee"]
                    .sudo()
                    .search([("company_id", "=", self.mode_company_id.id)])
                )
            for employee in employees:
                if not self.search(
                    [
                        ("employee_id", "=", employee.id),
                        ("holiday_status_id", "=", self.holiday_status_id.id),
                    ]
                ):
                    childs += self.with_context(
                        mail_notify_force_send=False, mail_activity_automation_skip=True
                    ).create(self._prepare_holiday_values(employee))
            # TODO is it necessary to interleave the calls?
            # childs.action_approve()
            for child in childs:
                while child.state != "done":
                    stage = child._get_next_stage(stage_type="next")
                    child.stage_id = stage
                    child._onchange_stage_id()
        return childs

    def action_refuse(self):
        for request in self:
            if request.stage_id and request.state == "in_progress":
                request.stage_id = request._get_next_stage(stage_type="cancel")
                request._onchange_stage_id()
                request.action_feedback()

    def _check_approval_update(self, state):
        return True

    def action_accept(self):
        """Send the request to be approved by the right users."""
        for rec in self:
            super(HolidaysAllocation, rec).action_accept()
            if rec.stage_id and rec.state == "done":
                rec._action_validate_create_childs()

    def get_nextcall(self, old_date=False):
        """Get next  call allocation."""
        today = datetime.today()
        # calculate interval unit
        if self.interval_unit == "days":
            delta = relativedelta(days=self.interval_number)
        elif self.interval_unit == "weeks":
            delta = relativedelta(weeks=self.interval_number)
        elif self.interval_unit == "months":
            delta = relativedelta(months=self.interval_number)
        else:
            delta = relativedelta(years=self.interval_number)
        date = (
            old_date
            if old_date
            else self.employee_id.date_direct_action
            or self.employee_id.create_date.date()
        )
        # calculate next call
        nextcall = date + delta
        while nextcall < today.date():
            nextcall = self.get_nextcall(nextcall)
        return nextcall

    @api.model
    def create(self, vals):
        allocation = super(HolidaysAllocation, self).create(vals)
        # update next call if allocation created from import
        if allocation.employee_id:
            if allocation.state == "done":
                allocation.stage_id = self.env["request.stage"].search(
                    [("res_model", "=", "hr.leave.allocation"), ("state", "=", "done")],
                    limit=1,
                )
            allocation.nextcall = allocation.get_nextcall()
        return allocation
