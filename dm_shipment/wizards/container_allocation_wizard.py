# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ContainerAllocationWizard(models.TransientModel):
    """Wizard for automatic container allocation
    
    Operates on shipment.subdeal_ids (primary relationship).
    Creates containers per subdeal with lines linked to subdeal's deal lines.
    """
    _name = 'container.allocation.wizard'
    _description = 'Container Allocation Wizard'
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        required=True
    )
    
    allocation_mode = fields.Selection([
        ('auto', 'Automatic (One Sub-Deal = One Container)'),
        ('manual', 'Manual Allocation')
    ], string='Allocation Mode',
        default='auto',
        required=True
    )
    
    # Requirements analysis (aggregated from subdeal lines)
    total_packages = fields.Float(
        compute='_compute_requirements',
        string='Total Packages'
    )
    
    total_weight = fields.Float(
        compute='_compute_requirements',
        string='Total Weight (kg)'
    )
    
    total_volume = fields.Float(
        compute='_compute_requirements',
        string='Total Volume (cbm)'
    )
    
    total_teu = fields.Float(
        compute='_compute_requirements',
        string='Total TEU Required'
    )
    
    requires_reefer = fields.Boolean(
        compute='_compute_requirements',
        string='Requires Reefer'
    )
    
    min_temp_required = fields.Float(
        compute='_compute_requirements',
        string='Min Temp Required (°C)'
    )
    
    max_temp_required = fields.Float(
        compute='_compute_requirements',
        string='Max Temp Required (°C)'
    )
    
    min_humidity_required = fields.Float(
        compute='_compute_requirements',
        string='Min Humidity Required (%)'
    )
    
    max_humidity_required = fields.Float(
        compute='_compute_requirements',
        string='Max Humidity Required (%)'
    )
    
    suggested_config = fields.Text(
        compute='_compute_suggestion',
        string='Suggested Configuration'
    )

    container_types_required = fields.Char(
        compute='_compute_requirements',
        string='Container Types',
        help='Container types from subdeal lines'
    )
    
    utilization_summary = fields.Html(
        compute='_compute_utilization_summary',
        string='Sub-Deal Utilization Summary'
    )
    
    @api.depends('shipment_id', 'shipment_id.subdeal_ids', 'shipment_id.subdeal_ids.line_ids')
    def _compute_requirements(self):
        """Analyze shipment requirements - aggregate from subdeal lines"""
        for wizard in self:
            if not wizard.shipment_id or not wizard.shipment_id.subdeal_ids:
                wizard.total_packages = 0.0
                wizard.total_weight = 0.0
                wizard.total_volume = 0.0
                wizard.total_teu = 0.0
                wizard.requires_reefer = False
                wizard.min_temp_required = 0.0
                wizard.max_temp_required = 0.0
                wizard.min_humidity_required = 0.0
                wizard.max_humidity_required = 0.0
                wizard.container_types_required = ''
                continue
            
            total_pkg = 0.0
            total_wgt = 0.0
            total_vol = 0.0
            total_teu_calc = 0.0
            needs_reefer = False
            temps = []
            humidities = []
            container_type_names = set()
            
            for subdeal in wizard.shipment_id.subdeal_ids:
                for line in subdeal.line_ids:
                    # Package count
                    total_pkg += line.quantity_packaging
                    
                    # Weight (from deal line)
                    total_wgt += line.weight or 0.0
                    
                    # TEU (from deal line if computed)
                    if hasattr(line, 'container_teu'):
                        total_teu_calc += line.container_teu or 0.0
                    
                    # Container type tracking
                    if hasattr(line, 'container_type_id') and line.container_type_id:
                        container_type_names.add(line.container_type_id.name)
                    
                    # Volume (best effort from product template)
                    product_tmpl = line.product_id.product_tmpl_id
                    if hasattr(product_tmpl, 'master_carton_id') and product_tmpl.master_carton_id:
                        master_carton = product_tmpl.master_carton_id
                        if hasattr(master_carton, 'packaging_volume_m3'):
                            pkg_volume = master_carton.packaging_volume_m3 or 0.0
                            total_vol += line.quantity_packaging * pkg_volume
                    
                    # Check if product needs refrigeration
                    # Method 1: Check product flag
                    if hasattr(product_tmpl, 'requires_reefer_container'):
                        if product_tmpl.requires_reefer_container:
                            needs_reefer = True
                            
                            # Get temperature requirements
                            if hasattr(product_tmpl, 'set_temperature_min'):
                                temps.append(product_tmpl.set_temperature_min)
                            if hasattr(product_tmpl, 'set_temperature_max'):
                                temps.append(product_tmpl.set_temperature_max)
                            
                            # Get humidity requirements
                            if hasattr(product_tmpl, 'set_humidity_min'):
                                humidities.append(product_tmpl.set_humidity_min)
                            if hasattr(product_tmpl, 'set_humidity_max'):
                                humidities.append(product_tmpl.set_humidity_max)
                    
                    # Method 2: Check if deal line's container type is reefer
                    if hasattr(line, 'container_type_id') and line.container_type_id:
                        if line.container_type_id.is_reefer:
                            needs_reefer = True
                    
                    # Method 3: Check product's effective container type
                    if hasattr(product_tmpl, 'effective_container_type_id') and product_tmpl.effective_container_type_id:
                        if product_tmpl.effective_container_type_id.is_reefer:
                            needs_reefer = True
            
            wizard.total_packages = total_pkg
            wizard.total_weight = total_wgt
            wizard.total_volume = total_vol
            wizard.total_teu = total_teu_calc
            wizard.requires_reefer = needs_reefer
            wizard.container_types_required = ', '.join(sorted(container_type_names)) if container_type_names else ''
            
            # Set temperature range from collected temps
            if temps:
                wizard.min_temp_required = min(temps)
                wizard.max_temp_required = max(temps)
            else:
                wizard.min_temp_required = 0.0
                wizard.max_temp_required = 0.0
            
            # Set humidity range from collected humidities
            if humidities:
                wizard.min_humidity_required = min(humidities)
                wizard.max_humidity_required = max(humidities)
            else:
                wizard.min_humidity_required = 0.0
                wizard.max_humidity_required = 0.0
    
    @api.depends('total_volume', 'total_weight', 'total_teu', 'requires_reefer', 
                 'min_temp_required', 'max_temp_required',
                 'min_humidity_required', 'max_humidity_required',
                 'allocation_mode')
    def _compute_suggestion(self):
        """Suggest container configuration"""
        for wizard in self:
            if wizard.allocation_mode != 'auto':
                wizard.suggested_config = 'Manual allocation mode selected'
                continue
            
            if not wizard.shipment_id or not wizard.shipment_id.subdeal_ids:
                wizard.suggested_config = 'No sub-deals in shipment'
                continue
            
            subdeal_count = len(wizard.shipment_id.subdeal_ids)
            
            suggestion = f"Automatic Allocation:\n"
            suggestion += f"• {subdeal_count} sub-deal(s) → {subdeal_count} container(s)\n"
            suggestion += f"• Total: {wizard.total_packages:.0f} packages, "
            suggestion += f"{wizard.total_weight:.0f} kg"
            
            if wizard.total_volume > 0:
                suggestion += f", {wizard.total_volume:.2f} cbm"
            
            if wizard.total_teu > 0:
                suggestion += f"\n• Estimated TEU: {wizard.total_teu:.2f}"
            
            suggestion += "\n"
            
            if wizard.requires_reefer:
                suggestion += f"• ⚠️ Reefer required\n"
                suggestion += f"  - Temp: {wizard.min_temp_required:.1f}°C - {wizard.max_temp_required:.1f}°C\n"
                
                if wizard.min_humidity_required > 0 or wizard.max_humidity_required > 0:
                    suggestion += f"  - Humidity: {wizard.min_humidity_required:.1f}% - {wizard.max_humidity_required:.1f}%\n"
            
            wizard.suggested_config = suggestion
    
    def action_create_containers_auto(self):
        """
        Auto-generate: One container per subdeal
        
        Container Type Selection:
        - Uses most restrictive type from subdeal lines
        - Reefer > Dry, Lower temp > Higher temp, HC > GP
        
        Reefer Settings:
        - Populates temp/humidity from product requirements
        - Uses most restrictive values (lowest min, highest max)
        
        Sprint 2B will add: Multi-container splitting, manual optimization
        """
        self.ensure_one()
        
        # Guard: Prevent re-allocation if containers already exist
        if self.shipment_id.container_ids:
            raise UserError(_(
                'Containers already planned for this shipment.\n\n'
                'To re-plan containers:\n'
                '1. Delete existing containers from the shipment\n'
                '2. Run "Plan Containers" again\n\n'
                'Existing containers: %d'
            ) % len(self.shipment_id.container_ids))
        
        if not self.shipment_id.subdeal_ids:
            raise UserError(_('No sub-deals in shipment'))
        
        containers_created = 0
        warnings = []
        
        for idx, subdeal in enumerate(self.shipment_id.subdeal_ids):
            # Get all container types from subdeal lines
            container_types = subdeal.line_ids.mapped('container_type_id')
            container_types = [ct for ct in container_types if ct]
            
            if not container_types:
                warnings.append(f"⚠️ Sub-deal {subdeal.name} (Deal: {subdeal.deal_id.name}): No container type specified")
                continue
            
            # Select most restrictive container type
            selected_type = self._select_most_restrictive_container_type(container_types)
            
            # Calculate utilization (from deal line containers_required)
            total_containers_needed = sum(subdeal.line_ids.mapped('containers_required'))
            utilization_pct = (total_containers_needed * 100) if total_containers_needed else 0
            
            # Warning thresholds
            if utilization_pct > 100:
                warnings.append(
                    f"⚠️ Sub-deal {subdeal.name} (Deal: {subdeal.deal_id.name}): Requires {total_containers_needed:.2f} containers "
                    f"but creating 1 ({utilization_pct:.0f}% - OVERFLOW!)"
                )
            elif utilization_pct < 70:
                warnings.append(
                    f"ℹ️ Sub-deal {subdeal.name} (Deal: {subdeal.deal_id.name}): Low utilization ({utilization_pct:.0f}% of 1 container)"
                )
            
            # Build container vals
            container_vals = {
                'shipment_id': self.shipment_id.id,
                'container_type_id': selected_type.id,
                'sequence': (idx + 1) * 10,
            }
            
            # Add reefer settings if reefer container
            if selected_type.is_reefer:
                temps_min = []
                temps_max = []
                humid_min = []
                humid_max = []
                
                for line in subdeal.line_ids:
                    product_tmpl = line.product_id.product_tmpl_id
                    
                    # Temperature requirements
                    if hasattr(product_tmpl, 'set_temperature_min') and product_tmpl.set_temperature_min:
                        temps_min.append(product_tmpl.set_temperature_min)
                    if hasattr(product_tmpl, 'set_temperature_max') and product_tmpl.set_temperature_max:
                        temps_max.append(product_tmpl.set_temperature_max)
                    
                    # Humidity requirements
                    if hasattr(product_tmpl, 'set_humidity_min') and product_tmpl.set_humidity_min:
                        humid_min.append(product_tmpl.set_humidity_min)
                    if hasattr(product_tmpl, 'set_humidity_max') and product_tmpl.set_humidity_max:
                        humid_max.append(product_tmpl.set_humidity_max)
                
                # Most restrictive: lowest min, highest max
                if temps_min or temps_max:
                    container_vals['temp_range_min'] = min(temps_min) if temps_min else 0.0
                    container_vals['temp_range_max'] = max(temps_max) if temps_max else 0.0
                    # Required temp: use the minimum (most restrictive for cold chain)
                    container_vals['temp_required'] = min(temps_min) if temps_min else 0.0
                
                if humid_min or humid_max:
                    container_vals['humidity_range_min'] = min(humid_min) if humid_min else 0.0
                    container_vals['humidity_range_max'] = max(humid_max) if humid_max else 0.0
                    container_vals['humidity_required'] = min(humid_min) if humid_min else 0.0
                
                _logger.info(
                    f"Reefer settings for subdeal {subdeal.name}: "
                    f"temp={container_vals.get('temp_required')}°C "
                    f"({container_vals.get('temp_range_min')}-{container_vals.get('temp_range_max')}°C), "
                    f"humidity={container_vals.get('humidity_required')}%"
                )
            
            # Create container
            container = self.env['dm.container'].create(container_vals)
            
            # Create container lines from subdeal lines
            for line in subdeal.line_ids:
                self.env['dm.container.line'].create({
                    'container_id': container.id,
                    'deal_line_id': line.id,
                    'quantity_planned': line.quantity_packaging,
                })
            
            containers_created += 1
            
            _logger.info(
                f"Created container {selected_type.name} for subdeal {subdeal.name} "
                f"(Deal: {subdeal.deal_id.name}, utilization: {utilization_pct:.0f}%)"
            )
        
        # Log to shipment with warnings
        message_body = _(
            '<b>🚢 Containers Planned</b><br/><br/>'
            'Created %d container(s) automatically<br/>'
            'Mode: One sub-deal per container<br/><br/>'
        ) % containers_created
        
        if warnings:
            message_body += '<b>Warnings:</b><br/>' + '<br/>'.join(warnings)
        
        self.shipment_id.message_post(
            body=message_body,
            subject=_('Containers Created'),
            message_type='notification'
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Shipment: %s') % self.shipment_id.name,
            'res_model': 'dm.shipment',
            'res_id': self.shipment_id.id,
            'view_mode': 'form',
            'target': 'current'
        }
    
    def _select_most_restrictive_container_type(self, container_types):
        """
        Select most restrictive container type from list.
        
        Priority:
        1. Reefer over dry
        2. Lower temperature (if reefer)
        3. Larger size (40 > 20)
        4. High cube over GP
        
        Architecture ready for Sprint 2B: Complex optimization logic
        """
        if not container_types:
            return None
        
        # Separate reefer vs dry
        reefer_types = [ct for ct in container_types if ct.is_reefer]
        dry_types = [ct for ct in container_types if not ct.is_reefer]
        
        # Reefer always wins if present
        if reefer_types:
            # Among reefers, pick largest
            return max(reefer_types, key=lambda ct: ct.teu_factor or 0)
        else:
            # Among dry, pick largest
            return max(dry_types, key=lambda ct: ct.teu_factor or 0)
            
    @api.depends('shipment_id', 'shipment_id.subdeal_ids', 'shipment_id.subdeal_ids.line_ids',
                 'shipment_id.subdeal_ids.line_ids.containers_required')
    def _compute_utilization_summary(self):
        """Show per-subdeal utilization for user review"""
        for wizard in self:
            if not wizard.shipment_id or not wizard.shipment_id.subdeal_ids:
                wizard.utilization_summary = '<p>No sub-deals</p>'
                continue
            
            lines = ['<table class="table table-sm">']
            lines.append('<tr><th>Sub-Deal</th><th>Deal</th><th>Container Type</th><th>Containers Needed</th><th>Status</th></tr>')
            
            for subdeal in wizard.shipment_id.subdeal_ids:
                # Get container type
                container_types = subdeal.line_ids.mapped('container_type_id')
                container_types = [ct for ct in container_types if ct]
                
                if container_types:
                    # Use helper method
                    selected = wizard._select_most_restrictive_container_type(container_types)
                    ctype_name = selected.name if selected else 'Unknown'
                else:
                    ctype_name = '<span class="text-danger">Not Specified</span>'
                
                # Calculate containers needed
                containers_needed = sum(subdeal.line_ids.mapped('containers_required'))
                
                # Status
                if containers_needed > 1.1:
                    status = f'<span class="text-danger">⚠️ Overflow ({containers_needed:.2f} containers)</span>'
                elif containers_needed < 0.7:
                    status = f'<span class="text-warning">ℹ️ Low ({containers_needed:.1f} containers)</span>'
                else:
                    status = f'<span class="text-success">✓ Good ({containers_needed:.1f} containers)</span>'
                
                # Deal name for reference
                deal_name = subdeal.deal_id.name if subdeal.deal_id else 'N/A'
                
                lines.append(
                    f'<tr><td>{subdeal.name}</td><td>{deal_name}</td><td>{ctype_name}</td>'
                    f'<td>{containers_needed:.2f}</td><td>{status}</td></tr>'
                )
            
            lines.append('</table>')
            wizard.utilization_summary = ''.join(lines)