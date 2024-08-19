from odoo.api import Environment


def migrate(cr, version):
    """Attach leave to attachment."""
    env = Environment(cr, 1, context={})
    for leave in (
        env["hr.leave"]
        .sudo()
        .with_context(active_test=False)
        .search([("attachment_ids", "!=", False)])
    ):
        leave.attachment_ids.filtered(lambda attachment: not attachment.res_id).write(
            {"res_id": leave.id}
        )
