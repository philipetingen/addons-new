from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    """
    Product enhancements for DonnaMello Distribution System.
    Most DM fields are on product.template level.
    """
    _inherit = 'product.product'
    
    # Only variant-specific DM fields here if needed
    dm_product_code = fields.Char(
        string='DM Product Code',
        help='Internal DonnaMello product code'
    )


class ProductTemplate(models.Model):
    """
    Product template enhancements for DonnaMello.
    Includes DM-specific configuration attributes and dynamic container logic.
    """
    _inherit = 'product.template'
    
    # ==========================================
    # DM-SPECIFIC CRITICAL FIELDS (ADDING MISSING)
    # ==========================================
    
    dm_consumer_unit_net_weight = fields.Char(
        string='Consumer Unit Net Weight',
        help='Net weight of individual consumer unit (e.g., "50g", "1.76 oz")'
    )
    
    dm_consumable_units_per_pack = fields.Char(
        string='Consumable Units per Pack',
        help='Number of consumable units per pack (e.g., "24 pieces", "12 bars")'
    )
    
    dm_ti_hi = fields.Char(
        string='TI/HI',
        help='Pallet configuration - Cases per layer (TI) × Layers per pallet (HI)'
    )
    
    dm_branding_design = fields.Selection([
        ('oem', 'OEM'),
        ('bulk', 'Bulk'),
        ('donna_mello', 'Donna Mello'),
    ], string='Branding/Design', 
       default='donna_mello',
       help='Branding and design type'
    )
    
    dm_coloring = fields.Selection([
        ('natural', 'Natural'),
        ('artificial', 'Artificial'),
    ], string='Coloring', 
       help='Type of coloring used'
    )
    
    dm_flavoring = fields.Selection([
        ('natural', 'Natural'),
        ('artificial', 'Artificial'),
    ], string='Flavoring', 
       help='Type of flavoring used'
    )

    # Production Planning
    production_lead_time_days = fields.Integer(
        string='Production Lead Time (Days)',
        default=14,
        help='Days from production start to RTS completion'
    )

    planning_buffer_days = fields.Integer(
        string='Planning Buffer (Days)',
        default=7,
        help='Safety buffer days before production start'
    )

    total_production_cycle = fields.Integer(
        string='Total Production Cycle',
        compute='_compute_total_production_cycle',
        store=True,
        help='Total days needed: lead time + buffer'
    )

    
    # ==========================================
    # DM-SPECIFIC PRODUCT ATTRIBUTES (KEEP EXISTING)
    # ==========================================
    
    # Note: Renamed from collection_ids to dm_collection_ids for consistency
    dm_collection_ids = fields.Many2many(
        'dm.collection',
        'product_collection_rel',
        'product_id',
        'collection_id',
        string='Collections',
        help='Product collections (Core, Christmas, Halloween, etc.)'
    )
    
    dm_package_type_id = fields.Many2one(
        'dm.package.type',
        string='Package Type',
        help='Primary package type (Bag, Box, etc.)'
    )
    
    dm_individual_packing_type_id = fields.Many2one(
        'dm.individual.packing.type',
        string='Individual Packing Type',
        help='Individual item packing type'
    )
    
    dm_texture_ids = fields.Many2many(
        'dm.texture',
        'product_texture_rel',
        'product_id',
        'texture_id',
        string='Textures',
        help='Product textures'
    )
    
    dm_stabilizer_ids = fields.Many2many(
        'dm.stabilizer',
        'product_stabilizer_rel',
        'product_id',
        'stabilizer_id',
        string='Stabilizers',
        help='Stabilizers used (pectine, gelatine, etc.)'
    )
    
    dm_taste_flavor_ids = fields.Many2many(
        'dm.taste.flavor',
        'product_taste_flavor_rel',
        'product_id',
        'taste_id',
        string='Taste/Flavors',
        help='Product taste and flavor profiles'
    )
    
    dm_shape_ids = fields.Many2many(
        'dm.shape',
        'product_shape_rel',
        'product_id',
        'shape_id',
        string='Shapes',
        help='Product shapes'
    )
    
    # Separate inner and coating colors (FIXING THIS)
    dm_inner_color_ids = fields.Many2many(
        'dm.color',
        'product_inner_color_rel',
        'product_id',
        'color_id',
        string='Inner Colors',
        help='Inner colors of the product'
    )
    
    dm_coating_color_ids = fields.Many2many(
        'dm.color',
        'product_coating_color_rel',
        'product_id',
        'color_id',
        string='Coating Colors',
        help='Coating colors of the product'
    )
    
    # Keep the existing generic color field for backward compatibility
    color_ids = fields.Many2many(
        'dm.color',
        'product_color_rel',
        'product_id',
        'color_id',
        string='Colors (Legacy)',
        help='Product colors - use Inner/Coating colors instead'
    )
    
    # ==========================================
    # COMPLIANCE (MAKE REQUIRED!)
    # ==========================================
    
    dm_compliant_for_ids = fields.Many2many(
        'dm.compliance.region',
        'product_compliance_region_rel',
        'product_id',
        'compliance_id',
        string='Compliant for',
        required=True,  # CRITICAL: This is a required field per spec
        help='Regions/standards this product is compliant for'
    )
    
    # Backward compatibility - map old field name if it exists
    compliance_region_ids = fields.Many2many(
        'dm.compliance.region',
        'product_compliance_region_rel',
        'product_id',
        'compliance_id',
        string='Compliance Regions (Legacy)',
        related='dm_compliant_for_ids',
        help='Use dm_compliant_for_ids instead'
    )
    
    # ==========================================
    # QUALITY CONTROL (KEEP EXISTING)
    # ==========================================
    
    qc_required = fields.Boolean(
        string='QC Required',
        default=False,
        help='Quality control is required for this product'
    )

    # ==========================================
    # REQUIRED QC & DOCUMENTS (KEEP AND EXTEND)
    # ==========================================

    # ADD THESE:
    required_qc_type_ids = fields.Many2many(
        'dm.qc_type',
        'product_qc_type_rel',
        'product_id',
        'qc_type_id',
        string='Required QC Types',
        help='Specific QC check types required for this product'
    )

    required_document_type_ids = fields.Many2many(
        'dm.document.type',
        'product_document_type_rel',
        'product_id',
        'document_type_id',
        string='Required Documents',
        help='Document types required for shipping this product'
    )

    # ==========================================
    # PRODUCT COMPATIBILITY
    # ==========================================

    incompatible_product_ids = fields.Many2many(
        'product.template',
        'product_incompatibility_rel',
        'product_id',
        'incompatible_id',
        string='Incompatible Products',
        help='Products that cannot be shipped in the same container'
    )
    
    # ==========================================
    # PRODUCTION & EXPIRY (KEEP EXISTING)
    # ==========================================
    
    production_to_expiry_days = fields.Integer(
        string='Production to Expiry (Days)',
        default=365,
        help='Days from production to expiry date'
    )
    
    shelf_life_days = fields.Integer(
        string='Shelf Life (Days)',
        default=365,
        help='Total shelf life in days'
    )
    
    min_remaining_shelf_life = fields.Float(
        string='Min Remaining Shelf Life %',
        default=50.0,
        help='Minimum acceptable remaining shelf life percentage at delivery'
    )
    
    # ==========================================
    # CONTAINER REQUIREMENTS (KEEP EXISTING)
    # ==========================================
    
    # Loading preferences
    palletized = fields.Boolean(
        string='Palletized',
        default=True,
        help='Product is shipped on pallets'
    )
    
    floor_loading_allowed = fields.Boolean(
        string='Floor Loading Allowed',
        compute='_compute_floor_loading_allowed',
        store=True,
        help='Product can be floor loaded (when not palletized)'
    )
    
    preferred_loading_pattern = fields.Selection([
        ('floor', 'Floor Loading'),
        ('pallet', 'Palletized'),
        ('mixed', 'Mixed Loading')
    ], string='Preferred Loading Pattern', 
       compute='_compute_loading_pattern',
       store=True)
    
    # Container preferences
    container_length_preference = fields.Selection([
        ('20', "20'"),
        ('40', "40'"),
        ('45', "45'"),
    ], string='Container Length', default='40')
    
    high_cube_capable = fields.Boolean(
        string='High Cube Capable',
        default=True,
        help='Product can be loaded in high cube containers'
    )
    
    requires_reefer_container = fields.Boolean(
        string='Requires Reefer Container',
        help='Product must be shipped in temperature-controlled container'
    )
    
    # ==========================================
    # CONTAINER TYPE DETERMINATION
    # ==========================================

    default_container_type_id = fields.Many2one(
        'dm.container.type',
        string='Default Container Type',
        compute='_compute_default_container_type_id',
        store=True,
        help='Automatically determined container type based on preferences'
    )

    container_type_override_id = fields.Many2one(
        'dm.container.type',
        string='Container Type Override',
        help='Manual override for container type selection'
    )

    effective_container_type_id = fields.Many2one(
        'dm.container.type',
        string='Effective Container Type',
        compute='_compute_effective_container_type_id',
        store=True,
        help='Final container type (override if set, otherwise default)'
    )

    container_type_fallback = fields.Char(
        string='Container Type (Calculated)',
        compute='_compute_container_type_fallback',
        help='Fallback display when no dm.container.type records exist'
    )

    # Computed field for backward compatibility (selection-based)
    default_container_type = fields.Selection([
        ('20GP', "20' General Purpose"),
        ('20RF', "20' Reefer"),
        ('40GP', "40' General Purpose"),
        ('40RF', "40' Reefer"),
        ('40HC', "40' High Cube"),
        ('40HR', "40' High Cube Reefer"),
        ('45HC', "45' High Cube")
    ], compute='_compute_default_container_type', store=True)
    
    # ==========================================
    # PACKAGE CONFIGURATION (3-TIER SYSTEM)
    # ==========================================
    
    master_carton_id = fields.Many2one(
        'product.packaging',
        string='Master Carton',
        domain="[('product_id', '=', id), ('standard_type_id.code', '=', 'CARTON')]",
        help='Link to the master carton packaging configuration'
    )
    
    cartons_per_pallet = fields.Integer(
        string='Cartons per Pallet',
        compute='_compute_cartons_per_pallet',
        store=True,
        readonly=False,
        help='Number of cartons per pallet (auto-filled from TI/HI if available)'
    )
    
    pallets_per_container = fields.Integer(
        string='Pallets per Container',
        help='Number of pallets that fit in the container'
    )
    
    cartons_per_container = fields.Integer(
        string='Cartons per Container',
        compute='_compute_cartons_per_container',
        store=True,
        readonly=False,
        help='Total cartons per container (auto-calculated for palletized, direct entry for floor-loaded)'
    )
    
    # ==========================================
    # PALLET DIMENSIONS & WEIGHT
    # ==========================================
    
    pallet_height_cm = fields.Float(
        string='Pallet Height (cm)',
        help='Total pallet height including pallet base (user-entered)'
    )
    
    pallet_net_weight_kg = fields.Float(
        string='Pallet Net Weight (kg)',
        compute='_compute_pallet_net_weight',
        store=True,
        readonly=False,
        help='Net cargo weight per pallet (auto-calculated from carton weight, user can override)'
    )
    
    pallet_cbm = fields.Float(
        string='Pallet Volume (CBM)',
        compute='_compute_pallet_cbm',
        store=True,
        readonly=False,
        digits=(10, 4),
        help='Net cargo volume per pallet (auto-calculated from carton CBM, user can override)'
    )
    
    # ==========================================
    # CONTAINER WEIGHT & VOLUME
    # ==========================================
    
    container_net_weight_kg = fields.Float(
        string='Container Net Weight (kg)',
        compute='_compute_container_net_weight',
        store=True,
        readonly=False,
        help='Net cargo weight per container (auto-calculated, user can override)'
    )
    
    container_cbm = fields.Float(
        string='Container Volume (CBM)',
        compute='_compute_container_cbm',
        store=True,
        readonly=False,
        digits=(10, 4),
        help='Net cargo volume per container (auto-calculated, user can override)'
    )
    
    # ==========================================
    # RELATED FIELDS FOR UI DISPLAY
    # ==========================================
    
    master_carton_weight = fields.Float(
        string='Master Carton Weight',
        related='master_carton_id.packaging_net_weight',
        readonly=True,
        help='Weight from master carton (for display only)'
    )
    
    master_carton_volume = fields.Float(
        string='Master Carton Volume',
        related='master_carton_id.packaging_volume_m3',
        readonly=True,
        help='Volume from master carton (for display only)'
    )
    
    # ==========================================
    # TEMPERATURE & HUMIDITY (KEEP EXISTING)
    # ==========================================
    
    set_temperature_min = fields.Float(
        string='Set Temperature Min (°C)',
        help='Minimum temperature setting for reefer container'
    )
    
    set_temperature_max = fields.Float(
        string='Set Temperature Max (°C)',
        help='Maximum temperature setting for reefer container'
    )
    
    set_temperature_optimal = fields.Float(
        string='Optimal Temperature (°C)',
        help='Optimal temperature for product storage'
    )
    
    set_humidity_min = fields.Float(
        string='Set Humidity Min (%)',
        help='Minimum humidity setting for reefer container'
    )
    
    set_humidity_max = fields.Float(
        string='Set Humidity Max (%)',
        help='Maximum humidity setting for reefer container'
    )
    
    # ==========================================
    # STACKING & LOADING (KEEP EXISTING)
    # ==========================================
    
    max_stacking_layers = fields.Integer(
        string='Max Stacking Layers',
        default=0,
        help='Maximum number of layers when stacking (0 = no limit)'
    )
    
    loading_priority = fields.Integer(
        string='Loading Priority',
        default=50,
        help='Priority for loading sequence (lower = load first)'
    )
    
    # ==========================================
    # KEEP ALL YOUR EXISTING METHODS
    # ==========================================

    @api.depends('production_lead_time_days', 'planning_buffer_days')
    def _compute_total_production_cycle(self):
        """Compute total production cycle time"""
        for product in self:
            product.total_production_cycle = (
                (product.production_lead_time_days or 14) + 
                (product.planning_buffer_days or 7)
            )
    
    @api.depends('dm_ti_hi')
    def _compute_cartons_per_pallet(self):
        """Auto-compute cartons per pallet from TI/HI if available"""
        for product in self:
            if product.dm_ti_hi and not product.cartons_per_pallet:
                ti_hi_data = product.parse_ti_hi()
                product.cartons_per_pallet = ti_hi_data.get('total', 0)
    
    @api.depends('cartons_per_pallet', 'pallets_per_container', 'palletized')
    def _compute_cartons_per_container(self):
        """Auto-compute cartons per container for palletized products"""
        for product in self:
            if product.palletized and product.cartons_per_pallet and product.pallets_per_container:
                # Palletized: multiply cartons/pallet × pallets/container
                product.cartons_per_container = product.cartons_per_pallet * product.pallets_per_container
            elif not product.palletized and not product.cartons_per_container:
                # Floor-loaded: leave empty for manual entry
                product.cartons_per_container = 0
    
    @api.depends('cartons_per_pallet', 'master_carton_id.packaging_net_weight', 'master_carton_id')
    def _compute_pallet_net_weight(self):
        """Auto-compute pallet net weight from carton weight"""
        for product in self:
            if product.cartons_per_pallet and product.master_carton_id and product.master_carton_id.packaging_net_weight:
                # Auto-calculate: cartons × carton_weight
                product.pallet_net_weight_kg = product.cartons_per_pallet * product.master_carton_id.packaging_net_weight
            elif not product.pallet_net_weight_kg:
                # No source data, leave empty for manual entry
                product.pallet_net_weight_kg = 0.0
    
    @api.depends('cartons_per_pallet', 'master_carton_id.packaging_volume_m3', 'master_carton_id')
    def _compute_pallet_cbm(self):
        """Auto-compute pallet CBM from carton volume"""
        for product in self:
            if product.cartons_per_pallet and product.master_carton_id and product.master_carton_id.packaging_volume_m3:
                # Auto-calculate: cartons × carton_volume (convert m³ to CBM)
                product.pallet_cbm = product.cartons_per_pallet * product.master_carton_id.packaging_volume_m3
            elif not product.pallet_cbm:
                # No source data, leave empty for manual entry
                product.pallet_cbm = 0.0
    
    @api.depends('cartons_per_container', 'master_carton_id.packaging_net_weight', 'master_carton_id', 
                 'pallets_per_container', 'pallet_net_weight_kg', 'palletized')
    def _compute_container_net_weight(self):
        """Auto-compute container net weight gracefully"""
        for product in self:
            if product.palletized and product.pallets_per_container and product.pallet_net_weight_kg:
                # Palletized: pallets × pallet_weight
                product.container_net_weight_kg = product.pallets_per_container * product.pallet_net_weight_kg
            elif product.cartons_per_container and product.master_carton_id and product.master_carton_id.packaging_net_weight:
                # Floor-loaded or fallback: cartons × carton_weight
                product.container_net_weight_kg = product.cartons_per_container * product.master_carton_id.packaging_net_weight
            elif not product.container_net_weight_kg:
                # No source data, leave empty for manual entry
                product.container_net_weight_kg = 0.0
    
    @api.depends('cartons_per_container', 'master_carton_id.packaging_volume_m3', 'master_carton_id',
                 'pallets_per_container', 'pallet_cbm', 'palletized')
    def _compute_container_cbm(self):
        """Auto-compute container CBM gracefully"""
        for product in self:
            if product.palletized and product.pallets_per_container and product.pallet_cbm:
                # Palletized: pallets × pallet_cbm
                product.container_cbm = product.pallets_per_container * product.pallet_cbm
            elif product.cartons_per_container and product.master_carton_id and product.master_carton_id.packaging_volume_m3:
                # Floor-loaded or fallback: cartons × carton_volume
                product.container_cbm = product.cartons_per_container * product.master_carton_id.packaging_volume_m3
            elif not product.container_cbm:
                # No source data, leave empty for manual entry
                product.container_cbm = 0.0

    
    @api.depends('palletized')
    def _compute_loading_pattern(self):
        """Set loading pattern based on palletized flag"""
        for record in self:
            record.preferred_loading_pattern = 'pallet' if record.palletized else 'floor'
    
    @api.depends('palletized')
    def _compute_floor_loading_allowed(self):
        """Floor loading allowed when not palletized"""
        for record in self:
            record.floor_loading_allowed = not record.palletized
    

    @api.depends('container_length_preference', 'requires_reefer_container', 'high_cube_capable')
    def _compute_default_container_type(self):
        """Calculate default container type code from preferences"""
        for product in self:
            length = product.container_length_preference or '40'
            reefer = product.requires_reefer_container
            hc = product.high_cube_capable
            
            if length == '20':
                product.default_container_type = '20RF' if reefer else '20GP'
            elif length == '45':
                product.default_container_type = '45HC'
            else:  # 40ft
                if reefer:
                    product.default_container_type = '40HR' if hc else '40RF'
                else:
                    product.default_container_type = '40HC' if hc else '40GP'

    @api.depends('default_container_type')
    def _compute_default_container_type_id(self):
        """Link to actual dm.container.type record with fallback"""
        ContainerType = self.env['dm.container.type']
        
        for product in self:
            if not product.default_container_type:
                product.default_container_type_id = False
                continue
            
            # Try to find matching container type
            # Parse the code: first 2 chars = size, rest = type
            code = product.default_container_type
            size = code[:2]  # '20', '40', '45'
            type_code = code[2:]  # 'GP', 'RF', 'HC', 'HR'
            
            # Build search domain
            domain = [('size_code', '=', size)]
            
            if type_code == 'GP':
                domain.append(('type_code', '=', 'GP'))
            elif type_code == 'HC':
                domain.append(('type_code', '=', 'HC'))
            elif type_code == 'RF':
                domain.append(('type_code', '=', 'RF'))
            elif type_code == 'HR':
                # High Cube Reefer - might be stored as RF with HC flag
                domain.append(('type_code', '=', 'RF'))
                domain.append(('is_reefer', '=', True))
            
            container_type = ContainerType.search(domain, limit=1)
            product.default_container_type_id = container_type if container_type else False

    @api.depends('container_type_override_id', 'default_container_type_id')
    def _compute_effective_container_type_id(self):
        """Use override if set, otherwise default"""
        for product in self:
            product.effective_container_type_id = (
                product.container_type_override_id or 
                product.default_container_type_id
            )

    @api.depends('effective_container_type_id', 'default_container_type')
    def _compute_container_type_fallback(self):
        """Provide fallback display when no container type records exist"""
        for product in self:
            if product.effective_container_type_id:
                product.container_type_fallback = False
            elif product.default_container_type:
                # Show calculated value as fallback
                type_names = {
                    '20GP': "20' General Purpose",
                    '20RF': "20' Reefer",
                    '40GP': "40' General Purpose",
                    '40RF': "40' Reefer",
                    '40HC': "40' High Cube",
                    '40HR': "40' High Cube Reefer",
                    '45HC': "45' High Cube"
                }
                product.container_type_fallback = f"{type_names.get(product.default_container_type, product.default_container_type)} (No container types configured)"
            else:
                product.container_type_fallback = "Not configured"
    
    @api.model
    def create(self, vals):
        """Set default compliance region to US if not specified"""
        if 'dm_compliant_for_ids' not in vals or not vals.get('dm_compliant_for_ids'):
            # Try to find US compliance region
            us_compliance = self.env['dm.compliance.region'].search([
                '|', 
                ('name', '=', 'US'),
                ('name', '=', 'United States')
            ], limit=1)
            if us_compliance:
                vals['dm_compliant_for_ids'] = [(6, 0, [us_compliance.id])]
        
        return super().create(vals)
    
    # ==========================================
    # NEW HELPER METHOD FOR TI/HI
    # ==========================================
    
    def parse_ti_hi(self):
        """Parse TI/HI string into cases per layer and layers per pallet
        
        Returns:
            dict: {'ti': cases_per_layer, 'hi': layers_per_pallet, 'total': total_cases}
        """
        self.ensure_one()
        
        if not self.dm_ti_hi:
            return {'ti': 0, 'hi': 0, 'total': 0}
        
        # Handle various formats: "10x8", "10×8", "10 x 8", "10 × 8"
        import re
        match = re.match(r'(\d+)\s*[x×]\s*(\d+)', self.dm_ti_hi)
        if match:
            ti = int(match.group(1))
            hi = int(match.group(2))
            return {'ti': ti, 'hi': hi, 'total': ti * hi}
        
        return {'ti': 0, 'hi': 0, 'total': 0}