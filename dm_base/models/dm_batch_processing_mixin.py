from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class DmBatchProcessingMixin(models.AbstractModel):
    """
    Batch processing mixin for handling large datasets efficiently.
    
    Per Appendix Section 10: Performance Optimizations
    """
    _name = 'dm.batch.processing.mixin'
    _description = 'DonnaMello Batch Processing Mixin'
    
    @api.model
    def process_in_batches(self, records, batch_size=100, operation=None, commit=True):
        """
        Process large recordsets in batches to avoid memory issues.
        
        Args:
            records: Recordset to process
            batch_size: Number of records per batch
            operation: Optional function to apply to each batch
            commit: Whether to commit after each batch
            
        Yields:
            Processed batches
        """
        total = len(records)
        processed = 0
        results = []
        
        _logger.info(f"Starting batch processing of {total} records in batches of {batch_size}")
        
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            
            try:
                # Process batch
                if operation:
                    batch_result = operation(batch)
                    results.append(batch_result)
                else:
                    yield batch
                
                processed += len(batch)
                
                # Commit to free memory if requested
                if commit and not self.env.context.get('no_commit'):
                    self.env.cr.commit()
                    _logger.debug(f"Committed batch {i//batch_size + 1}")
                
                # Log progress
                progress = (processed / total) * 100
                _logger.info(f"Processed {processed}/{total} records ({progress:.1f}%)")
                
            except Exception as e:
                _logger.error(f"Error processing batch at index {i}: {str(e)}")
                if not self.env.context.get('skip_batch_errors'):
                    raise
                    
        _logger.info(f"Batch processing complete: {processed} records processed")
        
        if operation:
            return results
    
    @api.model
    def bulk_create(self, values_list, batch_size=100):
        """
        Create multiple records efficiently in batches.
        
        Args:
            values_list: List of value dictionaries
            batch_size: Records per batch
            
        Returns:
            Created records
        """
        created_records = self.env[self._name]
        
        def create_batch(batch_values):
            """Create a batch of records"""
            batch_records = self.env[self._name]
            for values in batch_values:
                batch_records |= self.create(values)
            return batch_records
        
        # Process in batches
        for i in range(0, len(values_list), batch_size):
            batch = values_list[i:i + batch_size]
            created_records |= create_batch(batch)
            
            if not self.env.context.get('no_commit'):
                self.env.cr.commit()
        
        return created_records
    
    @api.model
    def bulk_write(self, records, values, batch_size=100):
        """
        Update multiple records efficiently in batches.
        
        Args:
            records: Records to update
            values: Dictionary of values to write
            batch_size: Records per batch
        """
        total = len(records)
        
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            batch.write(values)
            
            if not self.env.context.get('no_commit'):
                self.env.cr.commit()
            
            _logger.debug(f"Updated batch {i//batch_size + 1} ({len(batch)} records)")
    
    def parallel_compute(self, field_name, batch_size=100):
        """
        Compute a field in batches for better performance.
        
        Args:
            field_name: Name of computed field
            batch_size: Records per batch
        """
        if field_name not in self._fields:
            raise ValueError(f"Field {field_name} does not exist")
        
        field = self._fields[field_name]
        if not field.compute:
            raise ValueError(f"Field {field_name} is not a computed field")
        
        # Process computation in batches
        for batch in self.process_in_batches(self, batch_size=batch_size):
            # Trigger computation
            batch._compute_field_value(field)
            
            # Store if needed
            if field.store:
                batch.modified([field_name])
                batch.recompute()