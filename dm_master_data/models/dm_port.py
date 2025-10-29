from odoo import models, fields, api
import re


class DmPort(models.Model):
    """
    Port management for shipment routing.
    Includes seaports, dry ports, airports, and rail terminals.
    """
    _name = 'dm.port'
    _description = 'DonnaMello Port'
    _order = 'country_id, name'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(
        string='Port Name',
        required=True,
        tracking=True,
        help='Full name of the port'
    )
    
    code = fields.Char(
        string='Port Code',
        size=5,
        required=True,
        index=True,
        tracking=True,
        help='UN/LOCODE or standard port code'
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    port_type = fields.Selection([
        ('sea', 'Seaport'),
        ('dry', 'Dry Port'),
        ('air', 'Airport'),
        ('rail', 'Rail Terminal'),
        ('road', 'Road Terminal'),
        ('river', 'River Port')
    ], string='Port Type', default='sea', required=True, tracking=True)
    
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        required=True,
        tracking=True
    )
    
    state_id = fields.Many2one(
        'res.country.state',
        string='State',
        domain="[('country_id', '=', country_id)]"
    )
    
    city = fields.Char(
        string='City',
        help='City where port is located'
    )
    
    # Coordinates
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 6),
        help='GPS Latitude'
    )
    
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 6),
        help='GPS Longitude'
    )
    
    # Capabilities
    can_handle_reefer = fields.Boolean(
        string='Reefer Capable',
        default=True,
        help='Port can handle refrigerated containers'
    )
    
    can_handle_dangerous = fields.Boolean(
        string='DG Capable',
        default=True,
        help='Port can handle dangerous goods'
    )
    
    has_customs = fields.Boolean(
        string='Has Customs',
        default=True,
        help='Port has customs clearance facilities'
    )
    
    # Operational details
    timezone = fields.Selection(
        '_tz_get',
        string='Timezone',
        help='Port timezone for scheduling'
    )
    
    working_hours = fields.Char(
        string='Working Hours',
        help='Port operating hours'
    )
    
    # Constraints
    max_vessel_size = fields.Char(
        string='Max Vessel Size',
        help='Maximum vessel size/class'
    )
    
    max_container_weight = fields.Float(
        string='Max Container Weight (tons)',
        help='Maximum container weight port can handle'
    )
    
    # Contact information
    contact_person = fields.Char(string='Contact Person')
    contact_phone = fields.Char(string='Contact Phone')
    contact_email = fields.Char(string='Contact Email')
    
    # Notes
    notes = fields.Text(
        string='Notes',
        help='Additional information about the port'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    
    @api.depends('name', 'code', 'country_id')
    def _compute_display_name(self):
        """Compute display name as 'Code - Name (Country)'."""
        for port in self:
            parts = [port.code]
            if port.name:
                parts.append(port.name)
            if port.country_id:
                parts.append(f"({port.country_id.code})")
            port.display_name = " - ".join(filter(None, parts))
    
    @api.model
    def _tz_get(self):
        """Get timezone list."""
        return [(tz, tz) for tz in self.env['res.partner']._fields['tz'].get_values(self.env)]
    
    @api.constrains('code')
    def _check_code(self):
        """Validate port code format."""
        for port in self:
            if not port.code:
                continue
            # Port codes should be uppercase, 3-5 characters
            if not re.match(r'^[A-Z]{2}[A-Z0-9]{1,3}$', port.code):
                raise ValueError(
                    f"Port code '{port.code}' invalid. "
                    "Must be 3-5 uppercase letters/numbers starting with 2 letters."
                )
    
    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        """Validate GPS coordinates."""
        for port in self:
            if port.latitude:
                if not -90 <= port.latitude <= 90:
                    raise ValueError("Latitude must be between -90 and 90")
            if port.longitude:
                if not -180 <= port.longitude <= 180:
                    raise ValueError("Longitude must be between -180 and 180")
    
    def get_distance_to(self, other_port):
        """
        Calculate approximate distance to another port.
        Uses simple great circle distance formula.
        
        Args:
            other_port: Another dm.port record
            
        Returns:
            float: Distance in kilometers
        """
        import math
        
        self.ensure_one()
        other_port.ensure_one()
        
        if not all([self.latitude, self.longitude, other_port.latitude, other_port.longitude]):
            return 0.0
        
        # Convert to radians
        lat1 = math.radians(self.latitude)
        lon1 = math.radians(self.longitude)
        lat2 = math.radians(other_port.latitude)
        lon2 = math.radians(other_port.longitude)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth radius in kilometers
        r = 6371
        
        return c * r
    
    @api.model
    def get_route(self, origin_port_id, destination_port_id):
        """
        Get route information between two ports.
        
        Args:
            origin_port_id: Origin port ID
            destination_port_id: Destination port ID
            
        Returns:
            dict: Route information
        """
        origin = self.browse(origin_port_id)
        destination = self.browse(destination_port_id)
        
        if not origin or not destination:
            return {}
        
        distance = origin.get_distance_to(destination)
        
        # Estimate transit time based on port types
        if origin.port_type == 'sea' and destination.port_type == 'sea':
            # Assume average vessel speed of 20 knots
            transit_days = int(distance / (20 * 1.852 * 24)) + 1
        elif 'air' in [origin.port_type, destination.port_type]:
            # Air freight is faster
            transit_days = 1 if distance < 3000 else 2
        else:
            # Land transport
            transit_days = int(distance / 500) + 1
        
        return {
            'origin': origin.display_name,
            'destination': destination.display_name,
            'distance_km': distance,
            'estimated_transit_days': transit_days,
            'route_type': f"{origin.port_type} to {destination.port_type}"
        }