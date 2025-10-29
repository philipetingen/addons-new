from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmStateTransitionMixin(models.AbstractModel):
    """
    State transition mixin for consistent state management.
    
    Provides:
    - State field with common states
    - Transition validation
    - State change logging
    - Cancellation handling
    """
    _name = 'dm.state.transition.mixin'
    _description = 'DonnaMello State Transition Mixin'
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True, required=True)
    
    # State transition history
    state_history_ids = fields.One2many(
        'dm.state.history',
        'res_id',
        string='State History',
        domain=lambda self: [('model', '=', self._name)],
        auto_join=True
    )
    
    cancelled_date = fields.Datetime(
        string='Cancelled Date',
        readonly=True
    )
    
    cancelled_by = fields.Many2one(
        'res.users',
        string='Cancelled By',
        readonly=True
    )
    
    cancellation_reason = fields.Text(
        string='Cancellation Reason'
    )
    
    def _get_allowed_transitions(self):
        """
        Define allowed state transitions.
        To be overridden by implementing models.
        
        Returns:
            dict: Allowed transitions by current state
        """
        return {
            'draft': ['confirmed', 'cancelled'],
            'confirmed': ['in_progress', 'cancelled'],
            'in_progress': ['done', 'cancelled'],
            'done': [],  # No transitions from done
            'cancelled': []  # No transitions from cancelled
        }
    
    def _validate_state_transition(self, new_state):
        """
        Validate if state transition is allowed.
        
        Args:
            new_state: Target state
            
        Raises:
            UserError: If transition not allowed
        """
        self.ensure_one()
        
        allowed_transitions = self._get_allowed_transitions()
        current_allowed = allowed_transitions.get(self.state, [])
        
        if new_state not in current_allowed:
            raise UserError(
                f"Cannot transition from '{self.state}' to '{new_state}'. "
                f"Allowed transitions: {', '.join(current_allowed) if current_allowed else 'None'}"
            )
    
    def write(self, vals):
        """Override write to validate and log state transitions."""
        if 'state' in vals:
            new_state = vals['state']
            for record in self:
                old_state = record.state
                
                # Skip if no change
                if old_state == new_state:
                    continue
                
                # Validate transition
                record._validate_state_transition(new_state)
                
                # Log state change
                record._log_state_change(old_state, new_state)
                
                # Handle cancellation
                if new_state == 'cancelled':
                    vals.update({
                        'cancelled_date': fields.Datetime.now(),
                        'cancelled_by': self.env.user.id,
                    })
                    record._handle_cancellation()
        
        return super().write(vals)
    
    def _log_state_change(self, old_state, new_state):
        """
        Log state transition for audit trail.
        
        Args:
            old_state: Previous state
            new_state: New state
        """
        # Create history record
        self.env['dm.state.history'].sudo().create({
            'model': self._name,
            'res_id': self.id,
            'old_state': old_state,
            'new_state': new_state,
            'changed_by': self.env.user.id,
            'changed_date': fields.Datetime.now(),
        })
        
        # Post message
        state_labels = dict(self._fields['state'].selection)
        message = (
            f"State changed from <b>{state_labels.get(old_state, old_state)}</b> "
            f"to <b>{state_labels.get(new_state, new_state)}</b>"
        )
        self.message_post(body=message, subtype_xmlid='mail.mt_note')
        
        _logger.info(f"{self._name} ID {self.id}: State transition {old_state} -> {new_state}")
    
    def _handle_cancellation(self):
        """
        Handle record cancellation.
        To be overridden by implementing models for specific logic.
        """
        # This will be overridden to handle CASCADE cancellations
        pass
    
    def action_confirm(self):
        """Transition to confirmed state."""
        for record in self:
            if record.state != 'draft':
                raise UserError(f"Only draft records can be confirmed. Current state: {record.state}")
            record.state = 'confirmed'
        return True
    
    def action_cancel(self):
        """Cancel the record with reason."""
        for record in self:
            if record.state in ['done', 'cancelled']:
                raise UserError(f"Cannot cancel records in {record.state} state")
            
            # Open wizard for cancellation reason if configured
            if self.env.context.get('show_cancel_wizard'):
                return {
                    'name': 'Cancel Reason',
                    'type': 'ir.actions.act_window',
                    'res_model': 'dm.cancel.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_model': self._name,
                        'default_res_id': record.id,
                    }
                }
            else:
                record.state = 'cancelled'
        return True
    
    def action_reset_to_draft(self):
        """Reset to draft state (if allowed)."""
        for record in self:
            if record.state != 'cancelled':
                raise UserError("Only cancelled records can be reset to draft")
            
            # Check if any dependent records exist
            if hasattr(record, '_check_reset_allowed'):
                record._check_reset_allowed()
            
            record.state = 'draft'
            record.cancelled_date = False
            record.cancelled_by = False
            record.cancellation_reason = False
        return True


class DmStateHistory(models.Model):
    """State transition history for audit trail."""
    _name = 'dm.state.history'
    _description = 'State Transition History'
    _order = 'changed_date desc'
    _rec_name = 'display_name'
    
    model = fields.Char('Model', required=True, index=True)
    res_id = fields.Integer('Record ID', required=True, index=True)
    
    old_state = fields.Char('From State', required=True)
    new_state = fields.Char('To State', required=True)
    
    changed_by = fields.Many2one('res.users', 'Changed By', required=True)
    changed_date = fields.Datetime('Changed Date', required=True)
    
    display_name = fields.Char(
        'Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    @api.depends('model', 'res_id', 'old_state', 'new_state')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.model}({record.res_id}): {record.old_state} → {record.new_state}"