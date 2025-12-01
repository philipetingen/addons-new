# -*- coding: utf-8 -*-

# PHASE 1: Independent models
from . import dm_deal_template

# PHASE 2: Sub-deal model (NEW - must load before deal)
from . import dm_deal_subdeal

# PHASE 3: Core deal model (base)
from . import dm_deal

# PHASE 4: Deal extensions (extend dm.deal)
from . import dm_deal_milestones
from . import dm_deal_workflow
from . import dm_deal_production
from . import dm_deal_documents
from . import dm_deal_template_application

# PHASE 5: Sub-deal extensions
from . import dm_deal_subdeal_workflow

# PHASE 6: Deal lines (reference dm.deal.subdeal)
from . import dm_deal_line

# PHASE 7: Deal line extensions (extend dm.deal.line)
from . import dm_deal_line_quantities
from . import dm_deal_line_pricing
from . import dm_deal_line_lot

# PHASE 8: Deal-level totals (depend on line extension fields)
from . import dm_deal_totals

# PHASE 9: Standard Odoo extensions (extend sale.order, purchase.order)
from . import sale_order
from . import purchase_order
from . import stock_move
from . import account_move