# -*- coding: utf-8 -*-
{
    'name': "POS Pricelist Quick Switch",
    'version': '20.0.1.0.0',
    'category': 'Point of Sale',
    'summary': "Buttons in the POS top bar to quickly switch between the available pricelists",
    'description': "Shows the pricelists enabled in the POS settings "
                   "(Available Pricelists) as buttons next to the product "
                   "search box, so the cashier can switch the pricelist of "
                   "the current order with one tap. On small screens the "
                   "buttons become a dropdown list.",
    'author': 'Abu Bushi',
    'depends': ['point_of_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_pricelist_quick_switch/static/src/app/navbar/navbar.js',
            'pos_pricelist_quick_switch/static/src/app/navbar/navbar.xml',
            'pos_pricelist_quick_switch/static/src/app/navbar/navbar.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
