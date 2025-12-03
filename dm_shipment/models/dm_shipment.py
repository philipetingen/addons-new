# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmShipment(models.Model):
    """Shipment - Sprint 0 Foundation + Subdeal Refactoring + Milestone Architecture
    
    Container-centric shipment management linking multiple subdeals.
    Subdeal is the primary relationship; deal_ids computed for backward compatibility.
    Shipment owns milestone dates (2-layer: current/actual) for execution timeline.
    """
    _name = 'dm.shipment'
    _description = 'Shipment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc, id desc'
    
    # =========================================================================
    # CORE FIELDS
    # =========================================================================
    
    name = fields.Char(
        string='Shipment Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('loading', 'Loading'),
        ('loaded', 'Loaded'),
        ('departed', 'Departed'),
        ('arrived', 'Arrived'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ], string='Status',
        default='draft',
        required=True,
        tracking=True,
        help='Shipment lifecycle state'
    )
    
    # =========================================================================
    # MILESTONES - CURRENT (Planned)
    # =========================================================================
    
    loading_current = fields.Date(
        string='Loading (Planned)',
        tracking=True,
        help='Planned loading date for this shipment'
    )
    
    etd_current = fields.Date(
        string='ETD (Planned)',
        tracking=True,
        help='Planned departure date'
    )
    
    eta_current = fields.Date(
        string='ETA (Planned)',
        tracking=True,
        help='Planned arrival date'
    )
    
    delivery_current = fields.Date(
        string='Delivery (Planned)',
        tracking=True,
        help='Planned delivery date'
    )
    
    # =========================================================================
    # MILESTONES - ACTUAL
    # =========================================================================
    
    loading_actual = fields.Date(
        string='Loading (Actual)',
        tracking=True,
        readonly=True,
        help='Actual loading completion date (set by workflow)'
    )
    
    etd_actual = fields.Date(
        string='ETD (Actual)',
        tracking=True,
        readonly=True,
        help='Actual departure date (set by workflow)'
    )
    
    eta_actual = fields.Date(
        string='ETA (Actual)',
        tracking=True,
        readonly=True,
        help='Actual arrival date (set by workflow)'
    )
    
    delivery_actual = fields.Date(
        string='Delivery (Actual)',
        tracking=True,
        readonly=True,
        help='Actual delivery date (set by workflow)'
    )
    
    # =========================================================================
    # SUBDEAL RELATIONSHIPS (PRIMARY)
    # =========================================================================
    
    subdeal_ids = fields.Many2many(
        'dm.deal.subdeal',
        'dm_shipment_subdeal_rel',
        'shipment_id',
        'subdeal_id',
        string='Sub-Deals',
        help='Sub-deals included in this shipment'
    )
    
    subdeal_count = fields.Integer(
        string='# Sub-Deals',
        compute='_compute_subdeal_count',
        store=True
    )
    
    # =========================================================================
    # DEAL RELATIONSHIPS (COMPUTED FOR BACKWARD COMPATIBILITY)
    # =========================================================================
    
    deal_ids = fields.Many2many(
        'dm.deal',
        'dm_shipment_deal_rel',
        'shipment_id',
        'deal_id',
        string='Deals',
        compute='_compute_deal_ids',
        store=True,
        help='Deals included in this shipment (computed from subdeals)'
    )
    
    deal_count = fields.Integer(
        string='# Deals',
        compute='_compute_deal_ids',
        store=True
    )

    container_ids = fields.One2many(
        'dm.container',
        'shipment_id',
        string='Containers'
    )
    
    container_count = fields.Integer(
        string='# Containers',
        compute='_compute_container_count',
        store=True
    )
    
    total_teu = fields.Float(
        string='Total TEU',
        compute='_compute_total_teu',
        store=True,
        digits=(16, 2)
    )
    
    # =========================================================================
    # ROUTE INFO (COMPUTED FROM SUBDEALS)
    # =========================================================================
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        compute='_compute_route_info',
        store=True,
        help='Primary supplier (from subdeals)'
    )
    
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port (POL)',
        compute='_compute_route_info',
        store=True
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Discharge Port (POD)',
        compute='_compute_route_info',
        store=True
    )
    
    # =========================================================================
    # DISPLAY HELPERS
    # =========================================================================
    
    customer_po_numbers = fields.Char(
        string='Customer POs',
        compute='_compute_display_helpers',
        store=True,
        help='Comma-separated customer PO numbers'
    )
    
    product_names = fields.Text(
        string='Products',
        compute='_compute_display_helpers',
        store=True,
        help='List of products in shipment'
    )
    
    customer_ids = fields.Many2many(
        'res.partner',
        'dm_shipment_customer_rel',
        'shipment_id',
        'partner_id',
        string='Customers',
        compute='_compute_customer_product_ids',
        store=True,
        help='Customers from allocated deals'
    )

    product_ids = fields.Many2many(
        'product.product',
        'dm_shipment_product_rel',
        'shipment_id',
        'product_id',
        string='Products',
        compute='_compute_customer_product_ids',
        store=True,
        help='Products from allocated deals'
    )    
    
    # =========================================================================
    # COMPUTED METHODS
    # =========================================================================
    
    @api.depends('subdeal_ids')
    def _compute_subdeal_count(self):
        for shipment in self:
            shipment.subdeal_count = len(shipment.subdeal_ids)
    
    @api.depends('subdeal_ids', 'subdeal_ids.deal_id')
    def _compute_deal_ids(self):
        """Compute deals from subdeals for backward compatibility"""
        for shipment in self:
            deals = shipment.subdeal_ids.mapped('deal_id')
            shipment.deal_ids = deals
            shipment.deal_count = len(deals)

    @api.depends('container_ids')
    def _compute_container_count(self):
        for shipment in self:
            shipment.container_count = len(shipment.container_ids)
    
    @api.depends('container_ids', 'container_ids.container_teu')
    def _compute_total_teu(self):
        for shipment in self:
            shipment.total_teu = sum(shipment.container_ids.mapped('container_teu'))
    
    @api.depends('subdeal_ids', 'subdeal_ids.supplier_id', 
                 'subdeal_ids.deal_id.loading_port_id', 'subdeal_ids.deal_id.discharge_port_id')
    def _compute_route_info(self):
        """Compute route from subdeals - take first subdeal's deal values"""
        for shipment in self:
            if shipment.subdeal_ids:
                first_subdeal = shipment.subdeal_ids[0]
                shipment.supplier_id = first_subdeal.supplier_id
                # Ports are on deal level
                if first_subdeal.deal_id:
                    shipment.loading_port_id = first_subdeal.deal_id.loading_port_id
                    shipment.discharge_port_id = first_subdeal.deal_id.discharge_port_id
                else:
                    shipment.loading_port_id = False
                    shipment.discharge_port_id = False
            else:
                shipment.supplier_id = False
                shipment.loading_port_id = False
                shipment.discharge_port_id = False
    
    @api.depends('subdeal_ids', 'subdeal_ids.customer_po_number', 'subdeal_ids.line_ids.product_id')
    def _compute_display_helpers(self):
        """Compute display fields for list view"""
        for shipment in self:
            if shipment.subdeal_ids:
                # Customer PO numbers (from subdeal's related deal field)
                po_numbers = shipment.subdeal_ids.mapped('customer_po_number')
                po_numbers = [po for po in po_numbers if po]
                shipment.customer_po_numbers = ', '.join(po_numbers) if po_numbers else ''
                
                # Product names (unique) from subdeal lines
                products = set()
                for subdeal in shipment.subdeal_ids:
                    for line in subdeal.line_ids:
                        if line.product_id:
                            products.add(line.product_id.name)
                shipment.product_names = ', '.join(sorted(products)) if products else ''
            else:
                shipment.customer_po_numbers = ''
                shipment.product_names = ''
    
    @api.depends('deal_ids', 'deal_ids.customer_id', 'deal_ids.product_ids')
    def _compute_customer_product_ids(self):
        """Aggregate customers and products from allocated deals"""
        for shipment in self:
            shipment.customer_ids = shipment.deal_ids.mapped('customer_id')
            shipment.product_ids = shipment.deal_ids.mapped('product_ids')    
    
    # =========================================================================
    # CRUD METHODS
    # =========================================================================
    
    @api.model
    def create(self, vals):
        """Create shipment with sequence"""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('dm.shipment') or _('New')
        
        return super().create(vals)
    
    def write(self, vals):
        """Update with validation and milestone cascade"""
        # Lock check for subdeal modifications
        if 'subdeal_ids' in vals:
            for shipment in self:
                if shipment.state not in ['draft', 'confirmed']:
                    raise UserError(_(
                        'Cannot modify sub-deals for shipment in state "%s"'
                    ) % shipment.state)
        
        res = super().write(vals)
        
        # Skip cascade if coming from subdeal (prevent loops)
        if self.env.context.get('from_subdeal_cascade'):
            return res
        
        # Milestone fields that cascade to subdeals
        MILESTONE_CASCADE_FIELDS = {
            'loading_current': 'loading_current',
            'etd_current': 'etd_current',
            'eta_current': 'eta_current',
            'delivery_current': 'delivery_current',
            'loading_actual': 'loading_actual',
            'etd_actual': 'etd_actual',
            'eta_actual': 'eta_actual',
            'delivery_actual': 'delivery_actual',
        }
        
        # Check which milestone fields changed
        cascade_vals = {}
        for shipment_field, subdeal_field in MILESTONE_CASCADE_FIELDS.items():
            if shipment_field in vals:
                cascade_vals[subdeal_field] = vals[shipment_field]
        
        # Cascade to subdeals (which cascade to deals via their own write)
        if cascade_vals:
            for shipment in self:
                if not shipment.subdeal_ids:
                    continue
                
                # Build change log for chatter
                changes_log = []
                for field, new_val in cascade_vals.items():
                    field_label = field.replace('_current', '').replace('_actual', ' (actual)').upper()
                    changes_log.append(f"• {field_label}: {new_val or 'Cleared'}")
                
                # Cascade to subdeals
                shipment.subdeal_ids.with_context(
                    from_shipment_cascade=True,
                    skip_milestone_warnings=True
                ).write(cascade_vals)
                
                _logger.info(
                    f"Shipment {shipment.name}: Cascaded milestone changes to "
                    f"{len(shipment.subdeal_ids)} subdeals: {list(cascade_vals.keys())}"
                )
                
                # Log to shipment chatter
                shipment.message_post(
                    body=_(
                        '<b>📅 Milestones Updated</b><br/>'
                        '%s<br/><br/>'
                        '<em>Cascaded to %d sub-deal(s)</em>'
                    ) % ('<br/>'.join(changes_log), len(shipment.subdeal_ids)),
                    subject=_('Milestone Cascade'),
                    message_type='notification'
                )
        
        return res
    
    def unlink(self):
        """Prevent deletion of non-draft shipments"""
        for shipment in self:
            if shipment.state != 'draft':
                raise UserError(_(
                    'Cannot delete shipment in state "%s"'
                ) % shipment.state)
        
        return super().unlink()
    
    # =========================================================================
    # STATE MACHINE
    # =========================================================================
    
    def action_confirm(self):
        """Confirm shipment"""
        for shipment in self:
            if not shipment.subdeal_ids:
                raise UserError(_('Cannot confirm shipment without sub-deals'))
            
            shipment.write({'state': 'confirmed'})
            shipment.message_post(body=_('Shipment confirmed'))
    
    def action_start_loading(self):
        """Begin loading process"""
        for shipment in self:
            if shipment.state != 'confirmed':
                raise UserError(_('Only confirmed shipments can start loading'))
            
            if not shipment.container_ids:
                raise UserError(_('Plan containers before starting loading'))
            
            shipment.write({'state': 'loading'})
            shipment.message_post(body=_('Loading started'))
    
    def action_complete_loading(self):
        """Mark loading complete - Sprint 3 enhanced with stock finalization"""
        for shipment in self:
            if shipment.state != 'loading':
                raise UserError(_('Shipment must be in loading state'))
            
            # Validate all container lines have loaded quantities
            missing_actuals = []
            for container in shipment.container_ids:
                for line in container.line_ids:
                    if line.quantity_loaded <= 0:
                        missing_actuals.append(f"{container.name_get()[0][1]}: {line.product_id.name}")
            
            if missing_actuals:
                raise UserError(_(
                    'Some container lines missing loaded quantities:\n%s'
                ) % '\n'.join(missing_actuals[:5]))
            
            # Set loading actual date
            shipment.write({
                'state': 'loaded',
                'loading_actual': fields.Date.today()
            })
            shipment.message_post(body=_('Loading complete'))
            
            # Process each subdeal: update milestones, state, and finalize stock
            processed_subdeals = set()
            for subdeal in shipment.subdeal_ids:
                if subdeal.id in processed_subdeals:
                    continue
                
                processed_subdeals.add(subdeal.id)
                
                # Finalize stock documents (SO delivery, PO receipt)
                try:
                    subdeal.action_finalize_shipment()
                except Exception as e:
                    _logger.warning(
                        f"Failed to finalize stock for subdeal {subdeal.id}: {e}"
                    )
                
                # Progress subdeal state to shipped (cascades to deal automatically)
                if subdeal.state in ['confirmed', 'in_production', 'ready']:
                    subdeal.action_mark_shipped()

    def action_open_loading_wizard(self):
        """Open loading confirmation wizard"""
        self.ensure_one()
        
        if self.state != 'loading':
            raise UserError(_('Start loading before confirming quantities'))
        
        wizard = self.env['loading.confirmation.wizard'].with_context(
            active_id=self.id,
            active_model='dm.shipment'
        ).create({
            'shipment_id': self.id
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirm Loading: %s') % self.name,
            'res_model': 'loading.confirmation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_mark_departed(self):
        """Mark vessel departed - set ETD actual"""
        for shipment in self:
            if shipment.state != 'loaded':
                raise UserError(_('Complete loading before marking departure'))
            
            shipment.write({
                'state': 'departed',
                'etd_actual': fields.Date.today()
            })
            shipment.message_post(body=_('Vessel departed'))
            
            # Update ETD actual on subdeals (cascade)
            for subdeal in shipment.subdeal_ids:
                subdeal.with_context(from_shipment_cascade=True).write({
                    'etd_actual': fields.Date.today()
                })
    
    def action_mark_arrived(self):
        """Mark vessel arrived at destination - set ETA actual"""
        for shipment in self:
            if shipment.state != 'departed':
                raise UserError(_('Vessel must be departed before arrival'))
            
            shipment.write({
                'state': 'arrived',
                'eta_actual': fields.Date.today()
            })
            shipment.message_post(body=_('Vessel arrived'))
            
            # Update ETA actual on subdeals (cascade)
            for subdeal in shipment.subdeal_ids:
                subdeal.with_context(from_shipment_cascade=True).write({
                    'eta_actual': fields.Date.today()
                })
    
    def action_mark_delivered(self):
        """Mark shipment delivered - set delivery actual"""
        for shipment in self:
            if shipment.state != 'arrived':
                raise UserError(_('Vessel must arrive before delivery'))
            
            shipment.write({
                'state': 'delivered',
                'delivery_actual': fields.Date.today()
            })
            shipment.message_post(body=_('Shipment delivered'))
            
            # Update delivery actual on subdeals and trigger workflow
            for subdeal in shipment.subdeal_ids:
                subdeal.with_context(from_shipment_cascade=True).write({
                    'delivery_actual': fields.Date.today()
                })
                
                # Call subdeal workflow method if available
                if hasattr(subdeal, 'action_mark_delivered'):
                    subdeal.action_mark_delivered()
                elif subdeal.state != 'delivered':
                    subdeal.write({'state': 'delivered'})
    
    def action_cancel(self):
        """Cancel shipment - deallocate subdeals"""
        for shipment in self:
            if shipment.state == 'delivered':
                raise UserError(_('Cannot cancel delivered shipment'))
            
            # Deallocate subdeals
            for subdeal in shipment.subdeal_ids:
                subdeal.write({
                    'shipment_allocated': False,
                    'shipment_id': False
                })
            
            shipment.write({'state': 'cancelled'})
            shipment.message_post(body=_('Shipment cancelled, sub-deals deallocated'))
    
    def action_set_to_draft(self):
        """Reset to draft"""
        for shipment in self:
            if shipment.state == 'delivered':
                raise UserError(_('Cannot reset delivered shipment'))
            
            shipment.write({'state': 'draft'})
            shipment.message_post(body=_('Shipment reset to draft'))
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_view_deals(self):
        """View deals in this shipment"""
        self.ensure_one()
        
        return {
            'name': _('Deals: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.deal_ids.ids)],
            'context': {'create': False}
        }
        
    def action_view_containers(self):
        """View containers in this shipment"""
        self.ensure_one()
        
        return {
            'name': _('Containers: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'dm.container',
            'view_mode': 'tree,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id}
        }
    
    def action_plan_containers(self):
        """Open container planning wizard"""
        self.ensure_one()
        
        if not self.subdeal_ids:
            raise UserError(_('Add sub-deals to shipment before planning containers'))
        
        wizard = self.env['container.allocation.wizard'].create({
            'shipment_id': self.id
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Plan Containers: %s') % self.name,
            'res_model': 'container.allocation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new'
        }
    
    def action_reschedule(self):
        """Open shipment rescheduling wizard"""
        self.ensure_one()
        
        if self.state in ['cancelled', 'delivered']:
            raise UserError(_('Cannot reschedule %s shipment') % self.state)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reschedule: %s') % self.name,
            'res_model': 'shipment.reschedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': 'dm.shipment',
            }
        }