from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDealWorkflow(models.Model):
    """Deal Workflow Extension - Validation, Confirmation, Allocations"""
    _inherit = 'dm.deal'
    _description = 'Deal - Workflow Extension'
    
    # ============================================================
    # WORKFLOW ACTION METHODS
    # ============================================================
    
    def action_validate(self):
        """
        Phase 4B Step 1: Validate deal data completeness ONLY.
        
        Negotiation phase - does NOT create SO/PO yet.
        Commitment deferred to action_confirm().
        """
        for deal in self:
            if deal.state != 'draft':
                raise UserError(_('Only draft deals can be validated'))
            
            if not deal.line_ids:
                raise UserError(_('Cannot validate deal without product lines'))
            
            if not deal.customer_id:
                raise UserError(_('Customer is required'))
            
            if not deal.customer_po_number:
                raise UserError(_('Customer PO# is required'))
            
            # Data completeness checks
            for line in deal.line_ids:
                if not line.product_id:
                    raise UserError(_('All deal lines must have a product'))
                if not line.product_packaging_id:
                    raise UserError(_('All deal lines must have packaging defined'))
                if line.quantity_packaging <= 0:
                    raise UserError(_('All deal lines must have positive quantity'))
            
            # Set validation date
            deal.validation_date = fields.Date.today()
            
            # Move to validated state (NO document creation)
            deal.state = 'validated'
            
            deal.message_post(
                body=_('Deal validated - ready for confirmation.<br/>'
                       '<b>Note:</b> SO/PO will be created upon confirmation.'),
                subject=_('Deal Validated')
            )
            
            _logger.info(
                f"Deal {deal.name} validated by {self.env.user.name}. "
                f"SO/PO creation deferred to confirmation."
            )
        
        return True

    def action_confirm(self):
        """
        Phase 4B Step 1: Confirm deal and CREATE SO/PO.
        
        THIS is the commitment point - creates and confirms documents.
        """
        for deal in self:
            # Validation
            if deal.state != 'validated':
                raise UserError(_(
                    'Deal must be validated before confirmation.\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            # Create SO and PO
            try:
                # Create Sale Order
                so = deal._create_sale_order()
                
                # Create Purchase Order (if supplier set)
                po = False
                if deal.supplier_id:
                    po = deal._create_purchase_order()
                else:
                    _logger.info(f"No supplier set for deal {deal.name}, PO will be created later")
                
                # Auto-confirm documents
                if so and so.state == 'draft':
                    so.with_context(from_deal_confirm=True).action_confirm()
                    _logger.info(f"Auto-confirmed SO {so.name}")
                
                if po and po.state == 'draft':
                    po.with_context(from_deal_confirm=True).button_confirm()
                    _logger.info(f"Auto-confirmed PO {po.name}")
                
                # Set confirmation date
                if not deal.confirmation_date:
                    deal.confirmation_date = fields.Date.today()
                
                # Move to confirmed state
                deal.state = 'confirmed'
                
                # Create downpayment requests (if dm_financial installed)
                if hasattr(deal, '_create_downpayment_requests'):
                    try:
                        deal._create_downpayment_requests()
                    except Exception as e:
                        _logger.error(f"Error creating downpayments for deal {deal.name}: {str(e)}")
                
                # Create invoice split config (if dm_financial installed)
                if deal.invoice_split and hasattr(deal, '_create_invoice_split_config'):
                    try:
                        deal._create_invoice_split_config()
                    except Exception as e:
                        _logger.error(f"Error creating invoice split config: {str(e)}")
                
                # Generate cash flow projection (if dm_financial installed)
                if hasattr(deal, '_generate_cash_flow_projection'):
                    try:
                        deal._generate_cash_flow_projection()
                    except Exception as e:
                        _logger.error(f"Error generating cash flow: {str(e)}")
                
                deal.message_post(
                    body=_(
                        'Deal confirmed - commitment point reached.<br/>'
                        '<b>SO:</b> %s (confirmed)<br/>'
                        '<b>PO:</b> %s<br/>'
                        'Lines and prices are now locked.'
                    ) % (
                        so.name if so else 'N/A',
                        f"{po.name} (confirmed)" if po else 'Not created (no supplier)'
                    ),
                    subject=_('Deal Confirmed')
                )
                
                _logger.info(
                    f"Deal {deal.name} confirmed by {self.env.user.name}. "
                    f"SO: {so.name if so else 'N/A'}, "
                    f"PO: {po.name if po else 'N/A'}"
                )
                
            except Exception as e:
                _logger.error(f"Error confirming deal {deal.name}: {str(e)}")
                raise UserError(_(f"Failed to confirm deal: {str(e)}"))
        
        return True
    
    def _check_auto_confirmation(self):
        """
        DEPRECATED in Phase 4B: Auto-confirmation removed.
        Confirmation now requires explicit action_confirm() call.
        Kept for backward compatibility.
        """
        _logger.info("_check_auto_confirmation called but skipped (Phase 4B: explicit confirmation required)")
        return
    
    def action_cancel(self):
        """Cancel deal and related documents"""
        for deal in self:
            if deal.state in ['delivered', 'paid']:
                raise UserError(f"Cannot cancel deal in state '{deal.state}'.")
            
            # Handle cancellation cascade if available
            if hasattr(self.env, 'dm.cancellation.handler'):
                try:
                    self.env['dm.cancellation.handler'].handle_deal_cancellation(deal)
                except Exception as e:
                    _logger.warning(f"Cancellation handler error: {e}")
            
            # Cancel SO/PO
            for so in deal.sale_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                so.action_cancel()
            
            for po in deal.purchase_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                po.button_cancel()
            
            # Cancel allocations
            for alloc in deal.allocation_ids.filtered(lambda a: a.state == 'active'):
                try:
                    alloc.action_cancel()
                except Exception as e:
                    _logger.warning(f"Could not cancel allocation {alloc.id}: {e}")
            
            deal.state = 'cancelled'
            
            deal.message_post(
                body=f"Deal cancelled by {self.env.user.name}",
                subtype_xmlid='mail.mt_comment'
            )
        
        return True
    
    # ============================================================
    # ALLOCATION MANAGEMENT ACTIONS
    # ============================================================
    
    def action_unlock_production(self):
        """Cancel production allocation to unlock deal"""
        self.ensure_one()
        
        if not self.is_locked_for_production:
            raise UserError(_('Deal is not locked by production'))
        
        # Find and cancel production allocation
        pr_allocs = self.allocation_ids.filtered(
            lambda a: a.allocation_type == 'production' and a.state == 'active'
        )
        
        if not pr_allocs:
            self.is_locked_for_production = False
            return True
        
        pr_alloc = pr_allocs[0]
        pr = pr_alloc.production_run_id if hasattr(pr_alloc, 'production_run_id') else None
        
        if pr and pr.state not in ['draft', 'cancelled']:
            raise UserError(_(
                'Cannot unlock deal - production run %s is in state "%s".\n\n'
                'Cancel the production run first.'
            ) % (pr.name, pr.state))
        
        pr_alloc.action_cancel()
        
        self.message_post(
            body=f'Production allocation cancelled. Deal unlocked.',
            subtype_xmlid='mail.mt_comment'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Deal unlocked. Allocation to {pr.name if pr else "production"} cancelled.',
                'type': 'warning',
                'sticky': False,
            }
        }
    
    def action_unlock_shipment(self):
        """Cancel shipment allocation to unlock deal"""
        self.ensure_one()
        
        if not self.is_locked_for_shipment:
            raise UserError(_('Deal is not locked by shipment'))
        
        # Find and cancel shipment allocation
        ship_allocs = self.allocation_ids.filtered(
            lambda a: a.allocation_type == 'shipment' and a.state == 'active'
        )
        
        if not ship_allocs:
            self.is_locked_for_shipment = False
            return True
        
        ship_alloc = ship_allocs[0]
        ship = ship_alloc.shipment_id if hasattr(ship_alloc, 'shipment_id') else None
        
        if ship and ship.state not in ['draft', 'cancelled']:
            raise UserError(_(
                'Cannot unlock deal - shipment %s is in state "%s".\n\n'
                'Cancel the shipment first.'
            ) % (ship.name, ship.state))
        
        ship_alloc.action_cancel()
        
        self.message_post(
            body=f'Shipment allocation cancelled. Deal unlocked.',
            subtype_xmlid='mail.mt_comment'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': f'Deal unlocked. Allocation to {ship.name if ship else "shipment"} cancelled.',
                'type': 'warning',
                'sticky': False,
            }
        }
    
    def action_deallocate_all(self):
        """Cancel all active allocations"""
        self.ensure_one()
        active_allocations = self.allocation_ids.filtered(lambda a: a.state == 'active')
        if active_allocations:
            active_allocations.action_cancel()
            self.message_post(body=_("All allocations cancelled"))
            # Reset state to confirmed
            if self.state in ['allocated', 'partial', 'ready']:
                self.state = 'confirmed'
        return True
    
    # ============================================================
    # VIEW ACTION METHODS
    # ============================================================
    
    def action_view_sale_orders(self):
        """Open related sales orders"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_orders')
        action['domain'] = [('dm_deal_id', '=', self.id)]
        action['context'] = {'default_dm_deal_id': self.id}
        if len(self.sale_order_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.sale_order_ids.id
        return action

    def action_view_purchase_orders(self):
        """Open related purchase orders"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_form_action')
        action['domain'] = [('dm_deal_id', '=', self.id)]
        action['context'] = {'default_dm_deal_id': self.id}
        if len(self.purchase_order_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.purchase_order_ids.id
        return action

    def action_view_allocations(self):
        """Open allocation records"""
        self.ensure_one()
        return {
            'name': _('Deal Allocations'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.allocation',
            'view_mode': 'tree,form',
            'domain': [('deal_id', '=', self.id)],
            'context': {'default_deal_id': self.id},
        }