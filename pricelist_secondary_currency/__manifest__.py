{
    'name': 'Pricelist Secondary Currency',
    'summary': 'Price products in a secondary currency per pricelist; '
               'prices update automatically when the exchange rate changes',
    'description': """
Pricelist Secondary Currency
============================
* Each pricelist can define a secondary currency (e.g. USD).
* Fixed-price rules get a "Secondary Price" field; the fixed price in the
  pricelist currency is computed = secondary price x current exchange rate,
  rounded to the pricelist's secondary rounding (default: nearest whole number).
* When an exchange rate (res.currency.rate) is created, edited or deleted,
  all affected rules are recalculated automatically.
* A daily cron also refreshes prices (covers future-dated rates).
""",
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',
    'author': 'Abu Bushi',
    'depends': ['product'],
    'data': [
        'data/ir_cron.xml',
        'views/product_pricelist_views.xml',
    ],
    'installable': True,
    'application': False,
}
