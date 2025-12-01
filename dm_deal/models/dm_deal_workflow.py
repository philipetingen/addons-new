# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDealWorkflow(models.Model):
    """Deal Workflow Extension - All State Transitions
    
    Phase 0: Core workflow with subdeal support.
    
    Note: Production-related actions (action_start_production, action_mark_ready_to_ship)
    are in dm_deal_production.py extension.
    """
    _inherit = 'dm.deal'
    _description = 'Deal - Workflow Extension'
    
    # =========================================================================
    # VALIDATION (Deal-only, pre-subdeal)
    # =========================================================================
    
    def action_validate(self):
        """
        Validate deal data completeness ONLY.
        
        This is the negotiation phase - does NOT create SO/PO yet.
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
            
            # Create subdeal if doesn't exist
            if not deal.subdeal_ids:
                deal._create_primary_subdeal()
            
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
    
    # =========================================================================
    # CONFIRMATION (SO/PO Creation - Commitment Point)
    # =========================================================================
    
    def action_confirm(self):
        """
        Confirm deal and CREATE SO/PO.
        
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
    
    # =========================================================================
    # SHIPMENT WORKFLOW
    # =========================================================================
    
    def action_mark_shipped(self):
        """
        Mark deal as shipped.
        Will be automated by dm_shipment module when available.
        """
        for deal in self:
            if deal.state not in ['ready', 'in_production']:
                raise UserError(_(
                    'Can only mark deals as shipped when ready or in production.\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            deal.write({
                'state': 'shipped',
            })
            
            deal.message_post(
                body=_('Deal marked as shipped by %s') % self.env.user.name,
                subject=_('Deal Shipped'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} marked as shipped by {self.env.user.name}")
        
        return True
    
    def action_mark_delivered(self):
        """
        Mark deal as delivered.
        Will be automated by dm_shipment module when available.
        """
        for deal in self:
            if deal.state != 'shipped':
                raise UserError(_(
                    'Can only mark shipped deals as delivered.\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            deal.write({
                'state': 'delivered',
            })
            
            deal.message_post(
                body=_('Deal marked as delivered by %s') % self.env.user.name,
                subject=_('Deal Delivered'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} marked as delivered by {self.env.user.name}")
        
        return True
    
    # =========================================================================
    # COMPLETION (Deal-only, post-subdeal)
    # =========================================================================
    
    def action_complete(self):
        """
        Mark deal as completed - final closure by manager.
        FIXED: Must be in 'delivered' state, not 'confirmed'.
        """
        for deal in self:
            # FIXED: Check for 'delivered' state
            if deal.state != 'delivered':
                raise UserError(_(
                    'Can only complete deals that are delivered.\n\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            # Optional: Check for outstanding downpayments
            if hasattr(deal, 'downpayment_request_ids'):
                outstanding_dps = deal.downpayment_request_ids.filtered(
                    lambda dp: dp.state not in ['paid', 'cancelled']
                )
                if outstanding_dps:
                    raise UserError(_(
                        'Cannot complete deal with outstanding downpayment requests.\n\n'
                        'Outstanding requests: %s\n\n'
                        'Please settle or cancel them first.'
                    ) % ', '.join(outstanding_dps.mapped('name')))
            
            # Optional: Check for open activities
            if deal.activity_ids:
                raise UserError(_(
                    'Cannot complete deal with open activities.\n\n'
                    'Please close all activities first.'
                ))
            
            deal.write({'state': 'completed'})
            
            deal.message_post(
                body=_('Deal completed by %s') % self.env.user.name,
                subject=_('Deal Completed'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} marked as completed by {self.env.user.name}")
        
        return True
    
    def action_reopen(self):
        """Reopen a completed deal (for corrections)"""
        for deal in self:
            if deal.state != 'completed':
                raise UserError(_(
                    'Can only reopen completed deals.\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            # Move back to delivered state
            deal.write({'state': 'delivered'})
            
            deal.message_post(
                body=_('Deal reopened by %s') % self.env.user.name,
                subject=_('Deal Reopened'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} reopened by {self.env.user.name}")
        
        return True
    
    # =========================================================================
    # STATE CORRECTION (Move Backward)
    # =========================================================================
    
    def action_move_back(self):
        """
        Move deal back to previous state (for corrections).
        
        State Transitions Backward:
        - delivered → shipped
        - shipped → ready
        - ready → in_production
        - in_production → confirmed
        """
        STATE_BACKWARD_MAP = {
            'delivered': 'shipped',
            'shipped': 'ready',
            'ready': 'in_production',
            'in_production': 'confirmed',
        }
        
        for deal in self:
            current_state = deal.state
            
            if current_state not in STATE_BACKWARD_MAP:
                raise UserError(_(
                    'Cannot move back from state: %s'
                ) % dict(deal._fields['state'].selection).get(current_state))
            
            previous_state = STATE_BACKWARD_MAP[current_state]
            
            deal.write({
                'state': previous_state,
            })
            
            deal.message_post(
                body=_('Deal moved back from <b>%s</b> to <b>%s</b> by %s<br/>'
                       '<i>Reason: State correction</i>') % (
                    dict(deal._fields['state'].selection).get(current_state),
                    dict(deal._fields['state'].selection).get(previous_state),
                    self.env.user.name
                ),
                subject=_('Deal State Corrected'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.warning(
                f"Deal {deal.name} moved back from {current_state} to {previous_state} "
                f"by {self.env.user.name}"
            )
        
        return True
    
    # =========================================================================
    # CANCELLATION
    # =========================================================================
    
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
            
            deal.state = 'cancelled'
            
            deal.message_post(
                body=f"Deal cancelled by {self.env.user.name}",
                subtype_xmlid='mail.mt_comment'
            )
        
        return True
    
    def _check_auto_confirmation(self):
        """
        DEPRECATED in Phase 4B: Auto-confirmation removed.
        Confirmation now requires explicit action_confirm() call.
        Kept for backward compatibility.
        """
        _logger.info("_check_auto_confirmation called but skipped (Phase 4B: explicit confirmation required)")
        return
    
    # =========================================================================
    # VIEW ACTION METHODS
    # =========================================================================
    
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