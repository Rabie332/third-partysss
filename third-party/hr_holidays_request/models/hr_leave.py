from datetime import datetime, timedelta

from pytz import UTC

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools import float_compare

# from odoo.addons.resource.models.resource import HOURS_PER_DAY

class HolidaysRequest(models.Model):
    _name = "hr.leave"
    _inherit = ["request", "hr.leave"]

    def _default_employee(self):
        return self.env.context.get("default_employee_id") or self.env.user.employee_id

    @api.model
    def default_get(self, fields_list):
        defaults = super(HolidaysRequest, self).default_get(fields_list)
        defaults["state"] = "draft"
        return defaults

    def _employee_id_domain(self):
        if self.user_has_groups(
            "hr_holidays.group_hr_holidays_user"
        ) or self.user_has_groups("hr_holidays.group_hr_holidays_manager"):
            return []
        if self.user_has_groups("hr_holidays.group_hr_holidays_responsible"):
            return [("leave_manager_id", "=", self.env.user.id)]
        return [("user_id", "=", self.env.user.id)]

    stage_id = fields.Many2one(
        domain=lambda self: ""
        "[('res_model_id.model', '=', '" + self._name + "'), ('state', '!=', 'cancel'),"
        "'|', ('hr_leave_type_ids', '=', False), "
        "('hr_leave_type_ids', '=', holiday_status_id)]",
    )
    name = fields.Char(string="Description")
    specific_date = fields.Date(string="Specific Date")
    is_start_specific_date = fields.Boolean(
        string="The number of days starting from specific date",
        related="holiday_status_id.is_start_specific_date",
        store=True,
    )
    is_before_specific_date = fields.Boolean(
        string="Before specified date",
        related="holiday_status_id.is_before_specific_date",
        store=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Attachments",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    active = fields.Boolean(default=True)
    state = fields.Selection(
        selection_add=[
            ("confirm", "To Approve"),
            ("refuse", "Refused"),
            ("validate1", "Second Approval"),
            ("validate", "Approved"),
        ],
        tracking=False,
        default="draft",
    )

    employee_id = fields.Many2one(
        ondelete="restrict",
        default=_default_employee,
        tracking=True,
        domain=_employee_id_domain,
    )
    substitute_employee_id = fields.Many2one(
        "hr.employee",
        string="Substitute Employee",
        readonly=True,
        states={"draft": [("readonly", False)]},
    )
    holiday_phone = fields.Char(
        "Holiday Phone", readonly=True, states={"draft": [("readonly", False)]}
    )
    holiday_address = fields.Char(
        "Holiday Address", readonly=True, states={"draft": [("readonly", False)]}
    )
    refuse_reason = fields.Char(string="Refusal reason")
    number = fields.Char(string="Job number", readonly=1)
    holiday_status_id = fields.Many2one(
        readonly=True, states={"draft": [("readonly", False)]}
    )
    display_button_cancel = fields.Boolean(
        string="Cancel", compute="_compute_display_button"
    )

    def write(self, vals):
        """Relate attachments with the leave."""
        res = super(HolidaysRequest, self).write(vals)
        for leave in self:
            attachments = leave.attachment_ids.filtered(
                lambda attachment: not attachment.res_id
            )
            attachments.write({"res_id": leave.id})

        return res

    @api.onchange("holiday_status_id", "employee_id")
    def _onchange_holiday_status_id(self):
        self.state = "draft"

    def _sync_employee_details(self):
        super(HolidaysRequest, self)._sync_employee_details()
        for leave in self:
            if leave.employee_id:
                leave.number = leave.employee_id.number

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        super(HolidaysRequest, self)._onchange_employee_id()
        self.state = "draft"
        if self.employee_id:
            employee_ids = (
                self.env["hr.employee"]
                .search(
                    [
                        "|",
                        "|",
                        ("parent_id", "=", self.employee_id.id),
                        ("id", "=", self.employee_id.parent_id.id),
                        ("department_id", "=", self.employee_id.department_id.id),
                        ("id", "!=", self.employee_id.id),
                    ]
                )
                .ids
            )
            return {"domain": {"substitute_employee_id": [("id", "in", employee_ids)]}}

    def action_previous_stage(self):
        """Return the request to the previous stage."""
        for request in self:
            if request.stage_id and request.state in ["done", "in_progress"]:
                request.stage_id = request._get_previous_stage()
                request._onchange_stage_id()
                request.activity_update()

    @api.depends("stage_id")
    def _compute_display_button(self):
        for leave in self:
            super(HolidaysRequest, leave)._compute_display_button()
            users = leave._get_approvers()
            leave.display_button_send = False
            leave.display_button_refuse = False
            leave.display_button_accept = False
            leave.display_button_cancel = False
            leave.display_button_previous = False
            if leave.state == "draft" and (
                leave.env.user.has_group("hr.group_hr_manager")
                or leave.create_uid.id in users
                or leave.create_uid.id == leave.env.user.id
            ):
                leave.display_button_send = True
            elif leave.state == "in_progress" and (
                leave.env.uid in users
                or leave.env.user.has_group("hr.group_hr_manager")
            ):
                leave.display_button_accept = True
                leave.display_button_refuse = True
                leave.display_button_previous = True
            # display button cancel
            elif (
                leave.state == "done"
                and datetime.today().date() < leave.request_date_from
                and (
                    leave.env.user == leave.create_uid
                    or leave.env.user.has_group("hr.group_hr_manager")
                )
            ):
                leave.display_button_cancel = True
                leave.display_button_previous = True

    @api.depends("number_of_days")
    def _compute_number_of_hours_display(self):
        for holiday in self:
            calendar = holiday._get_calendar()
            if holiday.date_from and holiday.date_to:
                # Take attendances into account, in case the leave validated
                # Otherwise, this will result into number_of_hours = 0
                # and number_of_hours_display = 0 or (#day * calendar.hours_per_day),
                # which could be wrong if the employee doesn't work the same number
                # hours each day
                if holiday.state == "done":
                    start_dt = holiday.date_from
                    end_dt = holiday.date_to
                    if not start_dt.tzinfo:
                        start_dt = start_dt.replace(tzinfo=UTC)
                    if not end_dt.tzinfo:
                        end_dt = end_dt.replace(tzinfo=UTC)
                    intervals = calendar._attendance_intervals(
                        start_dt, end_dt, holiday.employee_id.resource_id
                    ) - calendar._leave_intervals(
                        start_dt, end_dt, None
                    )  # Substract Global Leaves
                    number_of_hours = sum(
                        (stop - start).total_seconds() / 3600
                        for start, stop, dummy in intervals
                    )
                else:
                    number_of_hours = holiday._get_number_of_days(
                        holiday.date_from, holiday.date_to, holiday.employee_id.id
                    )["hours"]
                holiday.number_of_hours_display = number_of_hours or (
                    holiday.number_of_days * (calendar.hours_per_day or HOURS_PER_DAY)
                )
            else:
                holiday.number_of_hours_display = 0

    def _check_approval_update(self, state):
        return True

    def _check_double_validation_rules(self, employees, state):
        return True

    @api.constrains("date_from", "date_to", "employee_id")
    def _check_date_state(self):
        return True

    @api.constrains("state", "number_of_days", "holiday_status_id")
    def _check_holidays(self):
        """The employee can take holidays if he don't have current solde."""
        for holiday in self:
            mapped_days = holiday.mapped("holiday_status_id").get_employees_days(
                holiday.mapped("employee_id").ids
            )
            allocation = (
                holiday.env["hr.leave.allocation"]
                .sudo()
                .search(
                    [
                        ("state", "=", "done"),
                        ("employee_id", "=", holiday.employee_id.id),
                        ("holiday_status_id", "=", holiday.holiday_status_id.id),
                    ],
                    limit=1,
                )
            )
            if (
                holiday.holiday_status_id.without_current_sold
                and allocation.allocation_type == "accrual"
            ):
                today = fields.Date.today()
                next_call = allocation.nextcall
                period_number = 0
                while (
                    next_call >= today
                    and next_call
                    <= datetime.strptime(
                        str(holiday.date_to), "%Y-%m-%d %H:%M:%S"
                    ).date()
                ):
                    next_call = allocation.get_nextcall(next_call)
                    period_number += 1
                if allocation.interval_unit == "days":
                    number_interval = (
                        period_number / allocation.interval_number
                    ) * allocation.number_per_interval
                elif allocation.interval_unit == "weeks":
                    number_interval = (
                        period_number / allocation.interval_number
                    ) * allocation.number_per_interval
                elif allocation.interval_unit == "months":
                    number_interval = (
                        period_number / allocation.interval_number
                    ) * allocation.number_per_interval
                else:
                    years_number = holiday.date_from.year - fields.Date.today().year
                    number_interval = (
                        years_number / allocation.interval_number
                    ) * allocation.number_per_interval
                future_solde = float(number_interval) + allocation.remaining_leaves
                if holiday.state == "draft":
                    if future_solde >= holiday.number_of_days:
                        return True
                    else:
                        raise ValidationError(
                            _(
                                "The number of remaining time off is not "
                                "sufficient for this time off type.\n"
                                "Please also check the time off waiting for validation."
                            )
                        )
                elif holiday.state == "done":
                    if (
                        float_compare(
                            future_solde + holiday.number_of_days, 0, precision_digits=2
                        )
                        == -1
                    ):
                        raise ValidationError(
                            _(
                                "The number of remaining time off is not "
                                "sufficient for this time off type.\n"
                                "Please also check the time off waiting for validation."
                            )
                        )
                    else:
                        return True
            else:
                if (
                    holiday.holiday_type != "employee"
                    or not holiday.employee_id
                    or holiday.holiday_status_id.allocation_type == "no"
                ):
                    continue
                leave_days = mapped_days[holiday.employee_id.id][
                    holiday.holiday_status_id.id
                ]
                if holiday.state == "draft":
                    if (
                        float_compare(
                            allocation.remaining_leaves,
                            holiday.number_of_days,
                            precision_digits=2,
                        )
                        == -1
                    ):
                        raise ValidationError(
                            _(
                                "The number of remaining time off is n"
                                "ot sufficient for this time off type.\n"
                                "Please also check the time off waiting for validation."
                            )
                        )
                else:
                    if (
                        float_compare(
                            leave_days["remaining_leaves"], 0, precision_digits=2
                        )
                        == -1
                        or float_compare(
                            leave_days["virtual_remaining_leaves"],
                            0,
                            precision_digits=2,
                        )
                        == -1
                    ):
                        raise ValidationError(
                            _(
                                "The number of remaining time off is "
                                "not sufficient for this time off type.\n"
                                "Please also check the time off waiting for validation."
                            )
                        )

    def _check_contract_validity(self):
        """Check period of holiday not depassed contract end."""
        contract = self.employee_id.contract_id
        if contract:
            today_date = datetime.today().date()
            if contract.date_end and contract.date_end < self.request_date_to:
                raise ValidationError(
                    _("The vacation period has exceeded contract end date.")
                )
            if (
                contract.sudo().first_contract_date
                and contract.sudo().first_contract_date > today_date
            ):
                raise ValidationError(
                    _("You are not permitted to submit a leave application.")
                )
            # check if the employee in test period
            if (
                self.employee_id
                and self.holiday_status_id.depassed_trial_period
                and self.request_date_from
                and contract.sudo().first_contract_date
            ):
                if contract.sudo().first_contract_date < today_date:
                    # calculate period between date today and contract date start
                    if (
                        (today_date - contract.sudo().first_contract_date).days < 90
                    ) or (
                        (
                            self.request_date_from - contract.sudo().first_contract_date
                        ).days
                        < 90
                    ):
                        raise ValidationError(
                            _(
                                "During the test period, it is not "
                                "permitted to submit a leave application"
                            )
                        )

    def _check_weekend_public_holidays(self):
        """Check if holiday request in weekend or public holidays."""
        contract = self.employee_id.contract_id
        if contract:
            # generate all dates from the holiday period
            all_dates = [
                str(self.request_date_from + timedelta(days=day))
                for day in range(
                    (self.request_date_to - self.request_date_from).days + 1
                )
            ]
            weekdays = [0, 1, 2, 3, 4, 5, 6]
            # get working days of employee by his contract
            working_weekdays = list(
                {
                    int(day)
                    for day in contract.resource_calendar_id.attendance_ids.mapped(
                        "dayofweek"
                    )
                }
            )
            # calculate not working days of employee by his contract
            not_working_weekdays = [
                day for day in weekdays if day not in working_weekdays
            ]
            # remove not working days from dates
            dates = [
                date
                for date in all_dates
                if fields.Date.from_string(date).weekday() in not_working_weekdays
                and fields.Date.from_string(date) >= contract.date_start
            ]
            if dates:
                raise ValidationError(_("It is not possible to apply on weekends."))
            # get the list of public holidays for this period

            hr_public_holiday_obj = self.env["hr.public.holiday"]
            inter = hr_public_holiday_obj.search([("state", "=", "done")])
            date_from = self.request_date_from
            date_to = self.request_date_to
            for public_holiday in inter:
                if (
                    public_holiday.date_from <= date_from <= public_holiday.date_to
                    or public_holiday.date_from <= date_to <= public_holiday.date_to
                    or date_from <= public_holiday.date_from <= date_to
                    or date_from <= public_holiday.date_to <= date_to
                ):
                    raise ValidationError(
                        _(
                            "It is not possible to apply on public holidays and holidays."
                        )
                    )

    @api.constrains("holiday_phone")
    def _check_holiday_phone(self):
        """Holiday Phone should contains only 10 numbers ."""
        for leave in self:
            if leave.holiday_phone:
                if not leave.holiday_phone.isdigit():
                    raise ValidationError(
                        _("Holiday phone should contains only numbers.")
                    )

    @api.constrains(
        "holiday_status_id",
        "request_date_from",
        "request_date_to",
        "specific_date",
        "employee_id",
    )
    def _check_leave_type_dates(self):
        for leave in self:
            if (
                leave.request_date_from
                and leave.request_date_to
                and leave.holiday_status_id
                and leave.employee_id
            ):
                leave._check_contract_validity()
                if leave.holiday_status_id.holidays_including_weekend_public:
                    leave._check_weekend_public_holidays()
                if (
                    leave.holiday_status_id.for_gender != leave.employee_id.gender
                    and leave.holiday_status_id.for_gender != "both"
                ):
                    if leave.holiday_status_id.for_gender == "male":
                        gender = _("Males")
                    else:
                        gender = _("Females")

                    raise ValidationError(
                        _("only %s can take %s ")
                        % (gender, leave.holiday_status_id.name)
                    )
                if (
                    leave.holiday_status_id.attachment_required
                    and not leave.attachment_ids
                ):
                    raise ValidationError(_("Please attach the necessary documents."))
                if leave.holiday_status_id.is_start_specific_date:
                    dates = [
                        (leave.specific_date + timedelta(days=day)).isoformat()
                        for day in range(leave.holiday_status_id.maximum_days)
                    ]
                    if str(leave.request_date_from) not in dates:
                        raise ValidationError(
                            _(
                                "You can request a holiday %s days from the specific date."
                            )
                            % (leave.holiday_status_id.maximum_days)
                        )
                    date_specific_end = leave.specific_date + timedelta(
                        days=leave.holiday_status_id.maximum_days
                    )
                    difference_days = (date_specific_end - leave.request_date_from).days
                    if leave.number_of_days > difference_days:
                        raise ValidationError(
                            _("You can only request %s days.") % (difference_days)
                        )
                if leave.holiday_status_id.is_before_specific_date:
                    date_request = leave.specific_date + timedelta(
                        days=-leave.holiday_status_id.days_before_specific_date
                    )
                    if leave.request_date_from != date_request:
                        raise ValidationError(
                            _(
                                "You should request a holiday before %s "
                                "days from the specific date."
                            )
                            % (leave.holiday_status_id.days_before_specific_date)
                        )

    def action_validate(self):
        """Do the treatment of action_validate of odoo
        without dealing with states and activities."""
        for holiday in self.filtered(
            lambda holiday: holiday.holiday_type != "employee"
        ):
            if holiday.holiday_type == "category":
                employees = holiday.category_id.employee_ids
            elif holiday.holiday_type == "company":
                employees = self.env["hr.employee"].search(
                    [("company_id", "=", holiday.mode_company_id.id)]
                )
            else:
                employees = holiday.department_id.member_ids

            conflicting_leaves = (
                self.env["hr.leave"]
                .with_context(
                    tracking_disable=True,
                    mail_activity_automation_skip=True,
                    leave_fast_create=True,
                )
                .search(
                    [
                        ("date_from", "<=", holiday.date_to),
                        ("date_to", ">", holiday.date_from),
                        ("state", "not in", ["cancel", "refuse"]),
                        ("holiday_type", "=", "employee"),
                        ("employee_id", "in", employees.ids),
                    ]
                )
            )

            if conflicting_leaves:
                # YTI: More complex use cases could be managed in master
                if holiday.leave_type_request_unit != "day" or any(
                    leave.leave_type_request_unit == "hour"
                    for leave in conflicting_leaves
                ):
                    raise ValidationError(
                        _("You can not have 2 leaves that overlaps on the same day.")
                    )

                for conflicting_leave in conflicting_leaves:
                    if (
                        conflicting_leave.leave_type_request_unit == "half_day"
                        and conflicting_leave.request_unit_half
                    ):
                        conflicting_leave.action_refuse()
                        continue
                    # Leaves in days
                    split_leaves = self.env["hr.leave"]
                    target_state = conflicting_leave.state
                    conflicting_leave.action_refuse()
                    if conflicting_leave.date_from < holiday.date_from:
                        before_leave_vals = conflicting_leave.copy_data(
                            {
                                "date_from": conflicting_leave.date_from.date(),
                                "date_to": holiday.date_from.date()
                                + timedelta(days=-1),
                            }
                        )[0]
                        before_leave = self.env["hr.leave"].new(before_leave_vals)
                        before_leave._onchange_request_parameters()
                        # Could happen for part-time contract, that time off is not necessary
                        # anymore.
                        # Imagine you work on monday-wednesday-friday only.
                        # You take a time off on friday.
                        # We create a company time off on friday.
                        # By looking at the last attendance before the company time off
                        # start date to compute the date_to,
                        # you would have a date_from > date_to.
                        # Just don't create the leave at that time. That's the reason why we use
                        # new instead of create. As the leave
                        # is not actually created yet, the sql
                        # constraint didn't check date_from < date_to yet.
                        if before_leave.date_from < before_leave.date_to:
                            split_leaves |= (
                                self.env["hr.leave"]
                                .with_context(
                                    tracking_disable=True,
                                    mail_activity_automation_skip=True,
                                    leave_fast_create=True,
                                )
                                .create(
                                    before_leave._convert_to_write(before_leave._cache)
                                )
                            )
                    if conflicting_leave.date_to > holiday.date_to:
                        after_leave_vals = conflicting_leave.copy_data(
                            {
                                "date_from": holiday.date_to.date() + timedelta(days=1),
                                "date_to": conflicting_leave.date_to.date(),
                            }
                        )[0]
                        after_leave = self.env["hr.leave"].new(after_leave_vals)
                        after_leave._onchange_request_parameters()
                        # Could happen for part-time contract, that time off is not necessary
                        # anymore.
                        if after_leave.date_from < after_leave.date_to:
                            split_leaves |= (
                                self.env["hr.leave"]
                                .with_context(
                                    tracking_disable=True,
                                    mail_activity_automation_skip=True,
                                    leave_fast_create=True,
                                )
                                .create(
                                    after_leave._convert_to_write(after_leave._cache)
                                )
                            )
                    for split_leave in split_leaves:
                        if target_state == "draft":
                            continue
                        if target_state == "done":
                            split_leave.action_validate()

            values = [
                holiday._prepare_holiday_values(employee) for employee in employees
            ]
            leaves = (
                self.env["hr.leave"]
                .with_context(
                    tracking_disable=True,
                    mail_activity_automation_skip=True,
                    leave_fast_create=True,
                )
                .create(values)
            )
            leaves.action_approve()
            # FIXME RLi: This does not make sense,
            #  only the parent should be in validation_type both
        employee_requests = self.filtered(lambda hol: hol.holiday_type == "employee")
        employee_requests._validate_leave_request()
        return True

    def action_accept(self):
        for leave in self:
            super(HolidaysRequest, leave).action_accept()
            # After the super is called check if the next
            # state is done to make the original "odoo" traitment.
            if leave.state == "done":
                leave.action_validate()
                allocation = leave.env["hr.leave.allocation"].search(
                    [
                        ("employee_id", "=", leave.employee_id.id),
                        ("state", "=", "done"),
                        ("holiday_status_id", "=", leave.holiday_status_id.id),
                    ],
                    limit=1,
                )
                if allocation:
                    if (
                        allocation.last_number_of_days
                        and allocation.last_number_of_days >= leave.number_of_days
                    ):
                        allocation.last_number_of_days -= leave.number_of_days
                    else:
                        allocation.last_number_of_days = 0
        return True

    @api.model
    def create(self, values):
        holiday = super(HolidaysRequest, self).create(values)
        employee_id = values.get("employee_id", False)
        # Fixme: we have deleted another create call with context:  Because it causes a bug.
        holiday_sudo = holiday.sudo()
        holiday_sudo.add_follower(employee_id)
        # Fixme: We have everything related to testing validation_type.
        attachments = holiday.attachment_ids.filtered(
            lambda attachment: not attachment.res_id
        )
        attachments.write({"res_id": holiday.id})
        return holiday

    def action_refuse(self):

        # Delete the meeting
        self.mapped("meeting_id").unlink()
        # If a category that created several holidays, cancel all related
        linked_requests = self.mapped("linked_request_ids")
        if linked_requests:
            linked_requests.action_refuse()

        # Post a second message, more verbose than the tracking message
        for holiday in self:
            if holiday.employee_id.user_id:
                holiday.message_post(
                    body=_("Your %s planned on %s has been refused")
                    % (holiday.holiday_status_id.display_name, holiday.date_from),
                    partner_ids=holiday.employee_id.user_id.partner_id.ids,
                )

        self._remove_resource_leave()
        return super(HolidaysRequest, self).action_refuse()

    def action_cancel(self):
        """Cancel a leave in state done."""
        for holiday in self:
            holiday.stage_id = holiday._get_next_stage(stage_type="cancel")
            holiday._onchange_stage_id()
            holiday.action_refuse()

    def name_get(self):
        res = []
        for request in self:
            if request.name:
                res.append((request.id, (request.name)))
            elif request.employee_id:
                res.append((request.id, (request.employee_id.name)))
        return res

    def _get_public_holidays_days(self, date_from, date_to, employee):
        public_holidays = self.env["hr.public.holiday"].search([("state", "=", "done")])
        public_holidays_days = 0
        # Check public holidays whom date_from or date_to are in leave period
        for holiday in public_holidays:
            if (
                date_from
                and date_to
                and (
                    holiday.date_from <= date_from <= holiday.date_to
                    or holiday.date_from <= date_to <= holiday.date_to
                    or date_from <= holiday.date_from <= date_to
                    or date_from <= holiday.date_to <= date_to
                )
            ):
                # calculate holiday days: Get intersection
                inter_date_from = date_from
                if holiday.date_from > date_from:
                    inter_date_from = holiday.date_from
                inter_date_to = date_to
                if holiday.date_to < date_to:
                    inter_date_to = holiday.date_to
                public_holidays_days = (inter_date_to - inter_date_from).days + 1
                if not self.holiday_status_id.count_weekend:
                    # Remove weekend days from public holidays
                    actual_days = employee._get_work_days_data(
                        datetime.combine(inter_date_from, datetime.min.time()),
                        datetime.combine(inter_date_to, datetime.max.time()),
                        calendar=employee.contract_id.resource_calendar_id,
                    )
                    actual_days = actual_days.get("days")
                    public_holidays_days -= public_holidays_days - actual_days
                if public_holidays_days < 0:
                    public_holidays_days = 0
        return public_holidays_days

    def _get_number_of_days(self, date_from, date_to, employee_id):
        """Returns a float equals to the timedelta between two dates given as string."""
        # count weekend days with holidays
        work_data = super(HolidaysRequest, self)._get_number_of_days(
            date_from, date_to, employee_id
        )
        if employee_id:
            employee = self.env["hr.employee"].sudo().browse(employee_id)
            if self.holiday_status_id.count_weekend:
                supposed_work_data = employee._get_work_days_data(
                    date_from,
                    date_to,
                    calendar=employee.contract_id.resource_calendar_id,
                )
                days = (date_to - date_from).days + 1
                weekend_days = days - supposed_work_data.get("days")
                work_data["days"] += weekend_days
            if not self.holiday_status_id.count_public_holidays:
                public_holidays_days = self._get_public_holidays_days(
                    self.request_date_from, self.request_date_to, employee
                )
                work_data["days"] -= public_holidays_days
        return work_data

    def action_approve(self):
        return True

    def _get_extra_domain(self):
        search_domain = []
        # append the domain of leave type to general domain
        if self.holiday_status_id:
            search_domain = expression.AND(
                [
                    search_domain,
                    [
                        "|",
                        ("hr_leave_type_ids", "=", False),
                        ("hr_leave_type_ids", "in", [self.holiday_status_id.id]),
                    ],
                ]
            )
        else:
            search_domain = expression.AND(
                [search_domain, [("hr_leave_type_ids", "=", False)]]
            )
        return search_domain
