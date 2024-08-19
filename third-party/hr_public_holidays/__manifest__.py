{
    "name": "Public Holidays",
    "version": "17.0.1.0.0",
    "author": "Hadooc",
    "depends": ["request","mail","hr"],
    "data": [
        "security/ir.model.access.csv",
        "data/hr_public_holiday_data.xml",
        "data/public_holidays_stage_data.xml",
        "views/hr_public_holidays_views.xml",
    ],
    "installable": True,
    "license": "AGPL-3",
}
