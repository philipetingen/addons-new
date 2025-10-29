from odoo import models, fields, api
from odoo.exceptions import UserError


class DmContainerType(models.Model):
    """
    Container type specifications for shipment planning.
    Enhanced with deletion protection and usage tracking.
    """
    _name = 'dm.container.type'
    _description = 'Container Type'
    _order = 'size_code, name'
    _rec_name = 'display_name'
    
    name = fields.Char(
        string='Container Type',
        required=True,
        help='Container type name (e.g., 20ft Standard, 40ft High Cube)'
    )
    
    size_code = fields.Selection([
        ('20', "20'"),
        ('40', "40'"),
        ('45', "45'"),
        ('10', "10'"),
        ('30', "30'"),
    ], string='Size', required=True)
    
    type_code = fields.Selection([
        ('GP', 'General Purpose'),
        ('HC', 'High Cube'),
        ('RF', 'Reefer'),
        ('OT', 'Open Top'),
        ('FR', 'Flat Rack'),
        ('TK', 'Tank'),
        ('PL', 'Platform'),
    ], string='Type Code', required=True, default='GP')
    
    iso_code = fields.Char(
        string='ISO Code',
        size=4,
        help='ISO 6346 size/type code (e.g., 22G1, 42R1)'
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    # Usage tracking - Made searchable with search method
    product_count = fields.Integer(
        string='Products Using This',
        compute='_compute_product_count',
        search='_search_product_count',  # Added search method
        help='Number of products using this container type'
    )
    
    is_system_default = fields.Boolean(
        string='System Default',
        default=False,
        help='System default container types cannot be deleted'
    )
    
    # External dimensions
    external_length = fields.Float(
        string='External Length (m)',
        digits=(16, 3),
        required=True,
        help='External length in meters'
    )
    
    external_width = fields.Float(
        string='External Width (m)',
        digits=(16, 3),
        required=True,
        default=2.438,  # Standard width
        help='External width in meters'
    )
    
    external_height = fields.Float(
        string='External Height (m)',
        digits=(16, 3),
        required=True,
        help='External height in meters'
    )
    
    # Internal dimensions (for cargo)
    internal_length = fields.Float(
        string='Internal Length (m)',
        digits=(16, 3),
        required=True,
        help='Internal usable length'
    )
    
    internal_width = fields.Float(
        string='Internal Width (m)',
        digits=(16, 3),
        required=True,
        help='Internal usable width'
    )
    
    internal_height = fields.Float(
        string='Internal Height (m)',
        digits=(16, 3),
        required=True,
        help='Internal usable height'
    )
    
    internal_volume = fields.Float(
        string='Internal Volume (m³)',
        compute='_compute_internal_volume',
        store=True,
        digits=(16, 2),
        help='Usable cargo volume'
    )
    
    # Door dimensions
    door_width = fields.Float(
        string='Door Width (m)',
        digits=(16, 3),
        help='Door opening width'
    )
    
    door_height = fields.Float(
        string='Door Height (m)',
        digits=(16, 3),
        help='Door opening height'
    )
    
    # Weight specifications
    tare_weight = fields.Float(
        string='Tare Weight (kg)',
        digits=(16, 0),
        required=True,
        help='Empty container weight'
    )
    
    max_gross_weight = fields.Float(
        string='Max Gross Weight (kg)',
        digits=(16, 0),
        required=True,
        help='Maximum total weight (container + cargo)'
    )
    
    max_payload = fields.Float(
        string='Max Payload (kg)',
        compute='_compute_max_payload',
        store=True,
        digits=(16, 0),
        help='Maximum cargo weight'
    )
    
    # Special features
    is_reefer = fields.Boolean(
        string='Refrigerated',
        compute='_compute_is_reefer',
        store=True,
        help='Container has refrigeration'
    )
    
    min_temperature = fields.Float(
        string='Min Temperature (°C)',
        help='Minimum temperature for reefer'
    )
    
    max_temperature = fields.Float(
        string='Max Temperature (°C)',
        help='Maximum temperature for reefer'
    )
    
    has_ventilation = fields.Boolean(
        string='Has Ventilation',
        default=False,
        help='Container has ventilation'
    )
    
    # Stowage
    max_stacking = fields.Integer(
        string='Max Stack Height',
        default=6,
        help='Maximum containers that can be stacked'
    )
    
    teu_factor = fields.Float(
        string='TEU Factor',
        compute='_compute_teu_factor',
        store=True,
        help='Twenty-foot Equivalent Units'
    )
    
    # Cost factors
    base_freight_rate = fields.Float(
        string='Base Freight Rate',
        digits=(16, 2),
        help='Base freight cost for this container type'
    )
    
    reefer_surcharge = fields.Float(
        string='Reefer Surcharge %',
        default=30.0,
        help='Additional charge for refrigerated containers'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    @api.depends('size_code', 'type_code', 'name')
    def _compute_display_name(self):
        """Compute display name."""
        for container in self:
            if container.size_code and container.type_code:
                container.display_name = f"{container.size_code}' {container.type_code} - {container.name}"
            else:
                container.display_name = container.name or 'New Container'
    
    @api.depends('internal_length', 'internal_width', 'internal_height')
    def _compute_internal_volume(self):
        """Calculate internal volume."""
        for container in self:
            if all([container.internal_length, container.internal_width, container.internal_height]):
                container.internal_volume = (
                    container.internal_length * 
                    container.internal_width * 
                    container.internal_height
                )
            else:
                container.internal_volume = 0.0
    
    @api.depends('max_gross_weight', 'tare_weight')
    def _compute_max_payload(self):
        """Calculate maximum payload."""
        for container in self:
            container.max_payload = container.max_gross_weight - container.tare_weight
    
    @api.depends('type_code')
    def _compute_is_reefer(self):
        """Determine if container is refrigerated."""
        for container in self:
            container.is_reefer = container.type_code == 'RF'
    
    @api.depends('size_code')
    def _compute_teu_factor(self):
        """Calculate TEU factor."""
        teu_map = {
            '10': 0.5,
            '20': 1.0,
            '30': 1.5,
            '40': 2.0,
            '45': 2.25,
        }
        for container in self:
            container.teu_factor = teu_map.get(container.size_code, 1.0)
    
    def _compute_product_count(self):
        """Count products using this container type."""
        ProductTemplate = self.env['product.template']
        for container in self:
            # Count products where this is default or override container
            count = ProductTemplate.search_count([
                '|',
                ('default_container_type_id', '=', container.id),
                ('container_type_override_id', '=', container.id)
            ])
            container.product_count = count
    
    def _search_product_count(self, operator, value):
        """
        Enable searching on product_count field.
        This allows the 'In Use' filter in search views to work.
        """
        # Get all container types with their product counts
        all_containers = self.search([])
        matching_ids = []
        
        for container in all_containers:
            # Calculate product count for this container
            count = self.env['product.template'].search_count([
                '|',
                ('default_container_type_id', '=', container.id),
                ('container_type_override_id', '=', container.id)
            ])
            
            # Check if it matches the search criteria
            if operator == '>' and count > value:
                matching_ids.append(container.id)
            elif operator == '>=' and count >= value:
                matching_ids.append(container.id)
            elif operator == '=' and count == value:
                matching_ids.append(container.id)
            elif operator == '!=' and count != value:
                matching_ids.append(container.id)
            elif operator == '<' and count < value:
                matching_ids.append(container.id)
            elif operator == '<=' and count <= value:
                matching_ids.append(container.id)
        
        return [('id', 'in', matching_ids)]
    
    @api.constrains('internal_length', 'internal_width', 'internal_height',
                    'external_length', 'external_width', 'external_height')
    def _check_dimensions(self):
        """Validate container dimensions."""
        for container in self:
            # Internal must be less than external
            if container.internal_length >= container.external_length:
                raise UserError("Internal length must be less than external length")
            if container.internal_width >= container.external_width:
                raise UserError("Internal width must be less than external width")
            if container.internal_height >= container.external_height:
                raise UserError("Internal height must be less than external height")
    
    def unlink(self):
        """
        Override unlink to prevent deletion of container types in use.
        """
        for container in self:
            # Check if system default
            if container.is_system_default:
                raise UserError(
                    f"Cannot delete '{container.display_name}' - it's a system default container type."
                )
            
            # Check if used by products
            if container.product_count > 0:
                raise UserError(
                    f"Cannot delete '{container.display_name}' - it's used by {container.product_count} product(s). "
                    f"Please reassign those products to different container types first."
                )

            # Check if used in any shipment containers
            container_count = self.env['dm.container'].search_count([
                ('container_type_id', '=', container.id)
            ])
            if container_count > 0:
                raise UserError(
                    f"Cannot delete '{container.display_name}' - it's used in {container_count} shipment container(s)."
                )
            
            # Check if there would be no containers left of this size
            remaining = self.search_count([
                ('size_code', '=', container.size_code),
                ('id', '!=', container.id)
            ])
            if remaining == 0:
                raise UserError(
                    f"Cannot delete '{container.display_name}' - it's the last container of size {container.size_code}'. "
                    f"At least one container type per size must remain."
                )
        
        return super().unlink()
    
    def write(self, vals):
        """
        Override write to prevent deactivating system defaults.
        """
        if 'active' in vals and not vals['active']:
            for container in self:
                if container.is_system_default:
                    raise UserError(
                        f"Cannot deactivate '{container.display_name}' - it's a system default container type."
                    )
                if container.product_count > 0:
                    raise UserError(
                        f"Cannot deactivate '{container.display_name}' - it's used by {container.product_count} product(s)."
                    )
        
        return super().write(vals)
    
    def calculate_utilization(self, total_volume, total_weight):
        """
        Calculate container utilization.
        Per Appendix Section 1.1: Container Fill Rate Calculation
        
        Args:
            total_volume: Total cargo volume in m³
            total_weight: Total cargo weight in kg
            
        Returns:
            dict: Utilization metrics
        """
        self.ensure_one()
        
        # Volume utilization
        volume_utilization = (total_volume / self.internal_volume * 100) if self.internal_volume else 0
        
        # Weight utilization
        weight_utilization = (total_weight / self.max_payload * 100) if self.max_payload else 0
        
        # Overall utilization (limiting factor)
        overall_utilization = max(volume_utilization, weight_utilization)
        
        return {
            'volume_utilization': round(volume_utilization, 1),
            'weight_utilization': round(weight_utilization, 1),
            'overall_utilization': round(overall_utilization, 1),
            'limiting_factor': 'weight' if weight_utilization > volume_utilization else 'volume',
            'is_valid': overall_utilization <= 100,
            'meets_minimum': overall_utilization >= 65,  # 65% minimum
        }
    
    def action_view_products(self):
        """
        Action to view products using this container type.
        """
        self.ensure_one()
        return {
            'name': f'Products using {self.display_name}',
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'tree,form',
            'domain': [
                '|',
                ('default_container_type_id', '=', self.id),
                ('container_type_override_id', '=', self.id)
            ],
            'context': {
                'default_container_type_override_id': self.id,
            }
        }
    
    @api.model
    def ensure_minimum_types(self):
        """
        Ensure minimum required container types exist.
        Called during module installation/upgrade.
        """
        required_types = [
            {
                'size_code': '20',
                'type_code': 'GP',
                'name': "20' General Purpose",
                'is_system_default': True,
                'external_length': 6.058,
                'external_width': 2.438,
                'external_height': 2.591,
                'internal_length': 5.898,
                'internal_width': 2.352,
                'internal_height': 2.393,
                'tare_weight': 2230,
                'max_gross_weight': 30480,
            },
            {
                'size_code': '40',
                'type_code': 'GP',
                'name': "40' General Purpose",
                'is_system_default': True,
                'external_length': 12.192,
                'external_width': 2.438,
                'external_height': 2.591,
                'internal_length': 12.032,
                'internal_width': 2.352,
                'internal_height': 2.393,
                'tare_weight': 3750,
                'max_gross_weight': 32500,
            },
            {
                'size_code': '40',
                'type_code': 'HC',
                'name': "40' High Cube",
                'is_system_default': True,
                'external_length': 12.192,
                'external_width': 2.438,
                'external_height': 2.896,
                'internal_length': 12.032,
                'internal_width': 2.352,
                'internal_height': 2.698,
                'tare_weight': 3940,
                'max_gross_weight': 32500,
            },
        ]
        
        for container_data in required_types:
            # Check if exists
            existing = self.search([
                ('size_code', '=', container_data['size_code']),
                ('type_code', '=', container_data['type_code'])
            ], limit=1)
            
            if not existing:
                self.create(container_data)