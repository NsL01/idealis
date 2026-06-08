{
    'name': 'Idealis - Collaborative Invoicing',
    'version': '19.0.1.0.0',
    'summary': 'Split payments among multiple contributors',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/account_move_collaborator_views.xml',
        'views/account_payment_register_views.xml',
        'views/report_collaborative_invoice.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'idealis_account/static/src/components/**/*',
        ],
    },
}
