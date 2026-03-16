# utils/delivery_schedule/data_loader.py - Data loading module for delivery data

import pandas as pd
import streamlit as st
from sqlalchemy import text
from ..db import get_db_engine
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DeliveryDataLoader:
    """Load and process delivery data from database"""
    
    def __init__(self):
        self.engine = get_db_engine()

    # ── Cached base loader (new) ─────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def load_base_data(_self, include_completed: bool = False):
        """Load base dataset from DB — only two variants ever cached.

        • include_completed=False  →  WHERE delivery_timeline_status != 'Completed'
        • include_completed=True   →  all rows

        Every other filter is applied client-side on this cached result.
        """
        try:
            query = """
            SELECT 
                delivery_id, dn_number, created_by_email, created_by_name,
                created_date, shipment_status, shipment_status_vn,
                dispatched_date, delivered_date, sto_delivery_status,
                sto_etd_date, is_delivered, delivery_confirmed,
                delivery_timeline_status, days_overdue, notify_email,
                reference_packing_list, shipping_cost, total_weight,
                oc_id, oc_number, oc_date, oc_line_id, oc_product_pn,
                standard_quantity, selling_quantity, uom_conversion, etd,
                product_id, product_pn, pt_code, package_size, brand,
                sto_dr_line_id, selling_stock_out_quantity,
                selling_stock_out_request_quantity, stock_out_quantity,
                stock_out_request_quantity, stockin_line_id, export_tax,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                total_instock_all_warehouses,
                total_instock_at_preferred_warehouse_valid,
                total_instock_all_warehouses_valid,
                gap_quantity, fulfill_rate_percent, fulfillment_status,
                product_total_remaining_demand, product_active_delivery_count,
                product_gap_quantity, product_fulfill_rate_percent,
                delivery_demand_percentage, product_fulfillment_status,
                customer, customer_code, customer_street, customer_zip_code,
                customer_state_province, customer_country_code,
                customer_country_name, customer_contact,
                customer_contact_email, customer_contact_phone,
                recipient_company, recipient_company_code, recipient_contact,
                recipient_contact_email, recipient_contact_phone,
                recipient_address, recipient_state_province,
                recipient_country_code, recipient_country_name,
                is_epe_company, intl_charge, local_charge,
                legal_entity, legal_entity_code,
                legal_entity_state_province, legal_entity_country_code,
                legal_entity_country_name, preferred_warehouse
            FROM delivery_full_view
            WHERE 1=1
            """

            if not include_completed:
                query += " AND delivery_timeline_status != 'Completed'"

            query += " ORDER BY delivery_id DESC, sto_dr_line_id DESC"

            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn)

            logger.info(
                f"[base_data] Loaded {len(df)} rows "
                f"(include_completed={include_completed})"
            )
            return df

        except Exception as e:
            logger.error(f"Error loading base data: {e}")
            return pd.DataFrame()

    # ── ETD Update ───────────────────────────────────────────────

    def update_delivery_etd(self, delivery_id, new_etd, updated_by="System", reason=""):
        """Update ETD for a delivery and log the change.

        Updates `stock_out_delivery.adjust_etd_date` — the view uses
        COALESCE(adjust_etd_date, etd_date) so this takes priority
        while preserving the original etd_date.

        Also inserts an audit row into `delivery_etd_change_log`.

        Parameters
        ----------
        delivery_id : int
            The delivery_id (= stock_out_delivery.id).
        new_etd : date
            New estimated time of delivery.
        updated_by : str
            Name of the user making the change.
        reason : str
            Optional reason / note.

        Returns
        -------
        (bool, str)  — success flag + message
        """
        try:
            with self.engine.begin() as conn:
                # 1. Fetch current ETD + DN for audit log
                old_row = conn.execute(
                    text("""
                        SELECT 
                            DATE(COALESCE(adjust_etd_date, etd_date)) AS current_etd,
                            dn_number
                        FROM stock_out_delivery
                        WHERE id = :did AND delete_flag = 0
                        LIMIT 1
                    """),
                    {"did": delivery_id},
                ).fetchone()

                if not old_row:
                    return False, f"Delivery ID {delivery_id} not found"

                old_etd = old_row[0]
                dn_number = old_row[1]

                # 2. Update adjust_etd_date (keeps original etd_date intact)
                result = conn.execute(
                    text("""
                        UPDATE stock_out_delivery
                        SET adjust_etd_date = :new_etd,
                            modified_date = NOW(),
                            etd_update_count = IFNULL(etd_update_count, 0) + 1
                        WHERE id = :did
                          AND delete_flag = 0
                    """),
                    {
                        "new_etd": new_etd,
                        "did": delivery_id,
                    },
                )

                rows_affected = result.rowcount

                if rows_affected == 0:
                    return False, f"No rows updated for delivery_id={delivery_id}"

                # 3. Audit log (create table if not exists — idempotent)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS delivery_etd_change_log (
                        id              BIGINT AUTO_INCREMENT PRIMARY KEY,
                        delivery_id     BIGINT NOT NULL,
                        dn_number       VARCHAR(50),
                        old_etd         DATE,
                        new_etd         DATE NOT NULL,
                        changed_by      VARCHAR(100) NOT NULL,
                        reason          TEXT,
                        changed_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_del_etdlog_delivery (delivery_id),
                        INDEX idx_del_etdlog_changed  (changed_at)
                    )
                """))

                conn.execute(
                    text("""
                        INSERT INTO delivery_etd_change_log
                            (delivery_id, dn_number, old_etd, new_etd, changed_by, reason)
                        VALUES
                            (:did, :dn, :old_etd, :new_etd, :changed_by, :reason)
                    """),
                    {
                        "did": delivery_id,
                        "dn": dn_number,
                        "old_etd": old_etd,
                        "new_etd": new_etd,
                        "changed_by": updated_by,
                        "reason": reason or None,
                    },
                )

            logger.info(
                f"[ETD Update] delivery_id={delivery_id} dn={dn_number} "
                f"old={old_etd} → new={new_etd} by {updated_by}"
            )
            return True, f"Updated DN {dn_number}"

        except Exception as e:
            logger.error(f"ETD update failed for delivery_id={delivery_id}: {e}")
            return False, str(e)

    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def load_delivery_data(_self, filters=None):
        """Load delivery data from delivery_full_view"""
        try:
            # Base query - Updated with brand field
            query = """
            SELECT 
                delivery_id,
                dn_number,
                created_by_email,
                created_by_name,
                created_date,
                shipment_status,
                shipment_status_vn,
                dispatched_date,
                delivered_date,
                sto_delivery_status,
                sto_etd_date,
                is_delivered,
                delivery_confirmed,
                delivery_timeline_status,
                days_overdue,
                notify_email,
                reference_packing_list,
                shipping_cost,
                total_weight,
                
                -- Order info
                oc_id,
                oc_number,
                oc_date,
                oc_line_id,
                oc_product_pn,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                etd,
                
                -- Product info
                product_id,
                product_pn,
                pt_code,
                package_size,
                brand,
                
                -- Stock info
                sto_dr_line_id,
                selling_stock_out_quantity,
                selling_stock_out_request_quantity,
                stock_out_quantity,
                stock_out_request_quantity,
                stockin_line_id,
                export_tax,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                total_instock_all_warehouses,
                gap_quantity,
                fulfill_rate_percent,
                fulfillment_status,
                
                -- New accurate gap analysis fields
                product_total_remaining_demand,
                product_active_delivery_count,
                product_gap_quantity,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                product_fulfillment_status,
                
                -- Customer info
                customer,
                customer_code,
                customer_street,
                customer_zip_code,
                customer_state_province,
                customer_country_code,
                customer_country_name,
                customer_contact,
                customer_contact_email,
                customer_contact_phone,
                
                -- Recipient info
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_code,
                recipient_country_name,
                
                -- Other info
                is_epe_company,
                intl_charge,
                local_charge,
                legal_entity,
                legal_entity_code,
                legal_entity_state_province,
                legal_entity_country_code,
                legal_entity_country_name,
                preferred_warehouse
                
            FROM delivery_full_view
            WHERE 1=1
            """
            
            # Apply filters if provided
            params = {}
            
            if filters:
                # Products filter with exclude option
                if filters.get('products'):
                    pt_codes = [p.split(' - ')[0] for p in filters['products']]
                    if filters.get('exclude_products', False):
                        query += " AND pt_code NOT IN :pt_codes"
                    else:
                        query += " AND pt_code IN :pt_codes"
                    params['pt_codes'] = tuple(pt_codes)
                
                # Brand filter with exclude option
                if filters.get('brands'):
                    if filters.get('exclude_brands', False):
                        query += " AND brand NOT IN :brands"
                    else:
                        query += " AND brand IN :brands"
                    params['brands'] = tuple(filters['brands'])
                    
                # Date range
                if filters.get('date_from'):
                    query += " AND etd >= :date_from"
                    params['date_from'] = filters['date_from']
                
                if filters.get('date_to'):
                    query += " AND etd <= :date_to"
                    params['date_to'] = filters['date_to']
                
                # Creators filter with exclude option
                if filters.get('creators'):
                    if filters.get('exclude_creators', False):
                        query += " AND created_by_name NOT IN :creators"
                    else:
                        query += " AND created_by_name IN :creators"
                    params['creators'] = tuple(filters['creators'])
                
                # Customers filter with exclude option
                if filters.get('customers'):
                    if filters.get('exclude_customers', False):
                        query += " AND customer NOT IN :customers"
                    else:
                        query += " AND customer IN :customers"
                    params['customers'] = tuple(filters['customers'])
                
                # Ship-to companies filter with exclude option
                if filters.get('ship_to_companies'):
                    if filters.get('exclude_ship_to_companies', False):
                        query += " AND recipient_company NOT IN :ship_to_companies"
                    else:
                        query += " AND recipient_company IN :ship_to_companies"
                    params['ship_to_companies'] = tuple(filters['ship_to_companies'])
                
                # States filter with exclude option
                if filters.get('states'):
                    if filters.get('exclude_states', False):
                        query += " AND recipient_state_province NOT IN :states"
                    else:
                        query += " AND recipient_state_province IN :states"
                    params['states'] = tuple(filters['states'])
                
                # Countries filter with exclude option
                if filters.get('countries'):
                    if filters.get('exclude_countries', False):
                        query += " AND recipient_country_name NOT IN :countries"
                    else:
                        query += " AND recipient_country_name IN :countries"
                    params['countries'] = tuple(filters['countries'])
                
                # Statuses filter with exclude option
                if filters.get('statuses'):
                    if filters.get('exclude_statuses', False):
                        query += " AND shipment_status NOT IN :statuses"
                    else:
                        query += " AND shipment_status IN :statuses"
                    params['statuses'] = tuple(filters['statuses'])
                
                # Legal entities filter with exclude option
                if filters.get('legal_entities'):
                    if filters.get('exclude_legal_entities', False):
                        query += " AND legal_entity NOT IN :legal_entities"
                    else:
                        query += " AND legal_entity IN :legal_entities"
                    params['legal_entities'] = tuple(filters['legal_entities'])
                
                # Timeline status filter with exclude option
                if filters.get('timeline_status'):
                    if filters.get('exclude_timeline_status', False):
                        query += " AND delivery_timeline_status NOT IN :timeline_status"
                    else:
                        query += " AND delivery_timeline_status IN :timeline_status"
                    params['timeline_status'] = tuple(filters['timeline_status'])
                
                # EPE Company filter (no exclude option needed as it's a radio button)
                if filters.get('epe_filter'):
                    if filters['epe_filter'] == 'EPE Companies Only':
                        query += " AND is_epe_company = 'Yes'"
                    elif filters['epe_filter'] == 'Non-EPE Companies Only':
                        query += " AND is_epe_company = 'No'"
                
                # Foreign customer filter (no exclude option needed as it's a radio button)
                if filters.get('foreign_filter'):
                    if filters['foreign_filter'] == 'Foreign Only':
                        query += " AND customer_country_code != legal_entity_country_code"
                    elif filters['foreign_filter'] == 'Domestic Only':
                        query += " AND customer_country_code = legal_entity_country_code"
            
            # Order by
            query += " ORDER BY delivery_id DESC, sto_dr_line_id DESC"
            
            # Execute query
            with _self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            logger.info(f"Loaded {len(df)} delivery records")
            return df
            
        except Exception as e:
            logger.error(f"Error loading delivery data: {e}")
            st.error(f"Failed to load delivery data: {str(e)}")
            return pd.DataFrame()

    def get_filter_options(self):
        """Derive filter options from cached base data — zero extra DB queries.

        Uses load_base_data(include_completed=True) which is already cached.
        All DISTINCT values are extracted via pandas in sub-second time,
        replacing the previous 11 separate SELECT DISTINCT queries.
        """
        try:
            # Reuse cached full dataset — no DB hit after first load
            df = self.load_base_data(include_completed=True)

            if df is None or df.empty:
                logger.warning("[filter_options] No base data — returning empty options")
                return {}

            options = {}

            # ── Simple DISTINCT columns ──────────────────────────────
            _simple_cols = {
                'creators':          'created_by_name',
                'customers':         'customer',
                'ship_to_companies': 'recipient_company',
                'states':            'recipient_state_province',
                'countries':         'recipient_country_name',
                'statuses':          'shipment_status',
                'timeline_statuses': 'delivery_timeline_status',
                'legal_entities':    'legal_entity',
                'brands':            'brand',
            }

            for key, col in _simple_cols.items():
                if col in df.columns:
                    options[key] = sorted(
                        df[col].dropna().unique().tolist()
                    )
                else:
                    options[key] = []

            # ── Products (CONCAT pt_code + product_pn) ───────────────
            if 'pt_code' in df.columns and 'product_pn' in df.columns:
                product_pairs = (
                    df[['pt_code', 'product_pn']]
                    .dropna()
                    .drop_duplicates()
                    .sort_values('pt_code')
                )
                options['products'] = [
                    f"{row['pt_code']} - {row['product_pn']}"
                    for _, row in product_pairs.iterrows()
                ]
            else:
                options['products'] = []

            # ── Date range (min/max ETD) ─────────────────────────────
            if 'etd' in df.columns:
                etd = pd.to_datetime(df['etd'], errors='coerce').dropna()
                if not etd.empty:
                    options['date_range'] = {
                        'min_date': etd.min().date(),
                        'max_date': etd.max().date(),
                    }
                else:
                    options['date_range'] = {
                        'min_date': datetime.now().date() - timedelta(days=365),
                        'max_date': datetime.now().date() + timedelta(days=365),
                    }
            else:
                options['date_range'] = {
                    'min_date': datetime.now().date() - timedelta(days=365),
                    'max_date': datetime.now().date() + timedelta(days=365),
                }

            # ── EPE Company options ──────────────────────────────────
            epe_options = ["All"]
            if 'is_epe_company' in df.columns:
                epe_values = df['is_epe_company'].dropna().unique().tolist()
                if 'Yes' in epe_values:
                    epe_options.append("EPE Companies Only")
                if 'No' in epe_values:
                    epe_options.append("Non-EPE Companies Only")
            options['epe_options'] = epe_options

            # ── Foreign / Domestic options ────────────────────────────
            foreign_options = ["All Customers"]
            if 'customer_country_code' in df.columns and 'legal_entity_country_code' in df.columns:
                has_domestic = (
                    df['customer_country_code'] == df['legal_entity_country_code']
                ).any()
                has_foreign = (
                    df['customer_country_code'] != df['legal_entity_country_code']
                ).any()
                if has_domestic:
                    foreign_options.append("Domestic Only")
                if has_foreign:
                    foreign_options.append("Foreign Only")
            options['foreign_options'] = foreign_options

            return options

        except Exception as e:
            logger.error(f"Error getting filter options: {e}")
            return {}

    def pivot_delivery_data(self, df, period='weekly'):
        """Pivot delivery data by period"""
        try:
            if df.empty:
                return pd.DataFrame()
            
            # Ensure etd is datetime
            df['etd'] = pd.to_datetime(df['etd'])
            
            # Create period column
            if period == 'daily':
                df['period'] = df['etd'].dt.date
                period_format = '%Y-%m-%d'
            elif period == 'weekly':
                df['period'] = df['etd'].dt.to_period('W').dt.start_time
                period_format = 'Week of %Y-%m-%d'
            else:  # monthly
                df['period'] = df['etd'].dt.to_period('M').dt.start_time
                period_format = '%B %Y'
            
            # Group by period and aggregate
            pivot_df = df.groupby(['period', 'customer', 'recipient_company']).agg({
                'delivery_id': 'count',
                'standard_quantity': 'sum',
                'remaining_quantity_to_deliver': 'sum',
                'gap_quantity': 'sum',
                'product_gap_quantity': 'sum',
                'product_total_remaining_demand': 'sum'
            }).reset_index()
            
            pivot_df.columns = ['Period', 'Customer', 'Ship To', 'Deliveries', 
                               'Total Quantity', 'Remaining to Deliver', 'Gap (Legacy)',
                               'Product Gap', 'Total Product Demand']
            
            # Format period
            pivot_df['Period'] = pd.to_datetime(pivot_df['Period']).dt.strftime(period_format)
            
            return pivot_df
            
        except Exception as e:
            logger.error(f"Error pivoting data: {e}")
            return pd.DataFrame()
   
    def get_sales_delivery_summary(self, creator_name, weeks_ahead=4):
        """Get delivery summary for a specific sales person - with line item details"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT 
                DATE(etd) as delivery_date,
                customer,
                customer_code,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                created_by_name,
                created_date
            FROM delivery_full_view
            WHERE created_by_name = :creator_name
                AND etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
            ORDER BY delivery_date, customer, delivery_id, sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'creator_name': creator_name,
                    'today': today,
                    'end_date': end_date
                })
            
            # Check for duplicate columns
            if not df.empty:
                duplicate_cols = df.columns[df.columns.duplicated()].tolist()
                if duplicate_cols:
                    logger.warning(f"Duplicate columns found in sales delivery summary: {duplicate_cols}")
                    # Remove duplicates
                    df = df.loc[:, ~df.columns.duplicated()]
                
                # Add total_quantity as alias for remaining_quantity_to_deliver
                df['total_quantity'] = df['remaining_quantity_to_deliver']
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting sales delivery summary: {e}")
            return pd.DataFrame()
    
    # All other methods remain the same...
    def get_sales_urgent_deliveries(self, creator_name):
        """Get overdue and due today deliveries for a specific sales person"""
        try:
            query = text("""
            SELECT 
                DATE(etd) as delivery_date,
                customer,
                customer_code,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                total_instock_all_warehouses,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                created_by_name,
                created_date
            FROM delivery_full_view
            WHERE created_by_name = :creator_name
                AND delivery_timeline_status IN ('Overdue', 'Due Today')
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
            ORDER BY 
                delivery_timeline_status DESC,  -- Overdue first, then Due Today
                days_overdue DESC,              -- Most overdue first
                delivery_date,
                customer,
                delivery_id,
                sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'creator_name': creator_name
                })
            
            # Check for duplicate columns
            if not df.empty:
                duplicate_cols = df.columns[df.columns.duplicated()].tolist()
                if duplicate_cols:
                    logger.warning(f"Duplicate columns found in urgent deliveries: {duplicate_cols}")
                    # Remove duplicates
                    df = df.loc[:, ~df.columns.duplicated()]
                
                # Add total_quantity as alias
                df['total_quantity'] = df['remaining_quantity_to_deliver']
                
                # Log summary
                overdue_count = df[df['delivery_timeline_status'] == 'Overdue']['delivery_id'].nunique()
                due_today_count = df[df['delivery_timeline_status'] == 'Due Today']['delivery_id'].nunique()
                logger.info(f"Loaded {overdue_count} overdue and {due_today_count} due today deliveries for {creator_name}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting urgent deliveries: {e}")
            return pd.DataFrame()
    
    def get_overdue_deliveries(self):
        """Get overdue deliveries that need attention"""
        try:
            query = text("""
            SELECT 
                delivery_id,
                dn_number,
                customer,
                recipient_company,
                etd,
                days_overdue,
                remaining_quantity_to_deliver,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                created_by_name,
                is_epe_company,
                brand
            FROM delivery_full_view
            WHERE delivery_timeline_status = 'Overdue'
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'ON_DELIVERY', 'DISPATCHED')
            ORDER BY days_overdue DESC, delivery_id DESC
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting overdue deliveries: {e}")
            return pd.DataFrame()
    
    def get_product_demand_analysis(self, product_id=None):
        """Get product demand analysis with accurate gap calculation"""
        try:
            query = """
            SELECT 
                product_id,
                product_pn,
                pt_code,
                brand,
                COUNT(DISTINCT delivery_id) as active_deliveries,
                SUM(remaining_quantity_to_deliver) as total_remaining_demand,
                MAX(total_instock_all_warehouses) as total_inventory,
                MAX(product_gap_quantity) as gap_quantity,
                MAX(product_fulfill_rate_percent) as fulfill_rate,
                MAX(product_fulfillment_status) as fulfillment_status,
                GROUP_CONCAT(DISTINCT customer SEPARATOR ', ') as customers
            FROM delivery_full_view
            WHERE remaining_quantity_to_deliver > 0
                AND shipment_status != 'DELIVERED'
            """
            
            params = {}
            if product_id:
                query += " AND product_id = :product_id"
                params['product_id'] = product_id
            
            query += " GROUP BY product_id, product_pn, pt_code, brand ORDER BY total_remaining_demand DESC"
            
            with self.engine.connect() as conn:
                df = pd.read_sql(text(query), conn, params=params)
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting product demand analysis: {e}")
            return pd.DataFrame()

    def get_product_demand_from_dataframe(self, df):
        """Calculate product demand analysis from filtered dataframe"""
        try:
            if df.empty:
                return pd.DataFrame()
            
            # Filter out delivered items to focus on active demand
            active_df = df[
                (df['remaining_quantity_to_deliver'] > 0) & 
                (~df['shipment_status'].isin(['DELIVERED', 'COMPLETED']))
            ].copy()
            
            if active_df.empty:
                logger.info("No active deliveries found after filtering")
                return pd.DataFrame()
            
            # Validate product-level metrics consistency
            product_metrics = ['product_gap_quantity', 'product_total_remaining_demand', 
                            'product_fulfill_rate_percent', 'product_fulfillment_status']
            
            # Check which metrics actually exist in the dataframe
            existing_metrics = [metric for metric in product_metrics if metric in active_df.columns]
            
            if not existing_metrics:
                logger.warning("No product-level metrics found in dataframe. Some analysis features may be limited.")
            
            for metric in existing_metrics:
                # Check for data availability
                non_null_count = active_df[metric].notna().sum()
                if non_null_count == 0:
                    logger.warning(f"{metric} column exists but contains no valid data")
                else:
                    # Check consistency
                    inconsistent = active_df.groupby('product_id')[metric].nunique()
                    inconsistent_products = inconsistent[inconsistent > 1]
                    if len(inconsistent_products) > 0:
                        logger.warning(f"Inconsistent {metric} values found for {len(inconsistent_products)} products")
            
            # Group by product to get aggregated metrics
            group_cols = ['product_id', 'product_pn', 'pt_code']
            if 'brand' in active_df.columns:
                group_cols.append('brand')
            
            agg_dict = {
                'delivery_id': 'nunique',
                'remaining_quantity_to_deliver': 'sum',
                'customer': lambda x: ', '.join(sorted(x.unique())[:5]),  # Top 5 customers
                'preferred_warehouse': 'nunique'  # Count of unique warehouses
            }
            
            # Add optional columns if they exist
            optional_aggs = {
                'oc_number': 'nunique',
                'total_instock_all_warehouses': lambda x: x.max() if x.notna().any() else 0,
                'total_instock_at_preferred_warehouse': lambda x: x.max() if x.notna().any() else 0,
                'product_gap_quantity': lambda x: x.max() if x.notna().any() else 0,
                'product_total_remaining_demand': lambda x: x.max() if x.notna().any() else 0,
                'product_fulfill_rate_percent': lambda x: x[x.notna()].mean() if x.notna().any() else None,
                'product_fulfillment_status': lambda x: (
                    'Out of Stock' if any(x == 'Out of Stock') 
                    else 'Can Fulfill Partial' if any(x == 'Can Fulfill Partial')
                    else 'Can Fulfill All' if any(x == 'Can Fulfill All')
                    else x.mode()[0] if len(x.mode()) > 0 
                    else (x.iloc[0] if len(x) > 0 else 'Unknown')
                ),
                'delivery_demand_percentage': lambda x: x[x.notna()].mean() if x.notna().any() else 0
            }
            
            for col, agg_func in optional_aggs.items():
                if col in active_df.columns:
                    agg_dict[col] = agg_func
            
            # Group by product
            product_analysis = active_df.groupby(group_cols).agg(agg_dict).reset_index()
            
            # Rename columns
            column_mapping = {
                'delivery_id': 'active_deliveries',
                'oc_number': 'unique_orders',
                'remaining_quantity_to_deliver': 'total_remaining_demand',
                'total_instock_all_warehouses': 'total_inventory',
                'total_instock_at_preferred_warehouse': 'preferred_warehouse_inventory',
                'product_gap_quantity': 'gap_quantity',
                'product_total_remaining_demand': 'product_total_demand',
                'product_fulfill_rate_percent': 'fulfill_rate',
                'product_fulfillment_status': 'fulfillment_status',
                'delivery_demand_percentage': 'avg_demand_percentage',
                'customer': 'top_customers',
                'preferred_warehouse': 'warehouse_count'
            }
            
            # Apply column renaming for columns that exist
            product_analysis = product_analysis.rename(columns=column_mapping)
            
            # Sort by gap quantity (descending) to show most critical products first
            if 'gap_quantity' in product_analysis.columns:
                product_analysis = product_analysis.sort_values('gap_quantity', ascending=False)
                
                # Add gap percentage calculation
                product_analysis['gap_percentage'] = (
                    product_analysis['gap_quantity'].abs() / 
                    product_analysis['total_remaining_demand'].replace(0, 1) * 100
                )
            else:
                # If no gap_quantity, sort by total_remaining_demand
                product_analysis = product_analysis.sort_values('total_remaining_demand', ascending=False)
            
            # After aggregation, recalculate fulfillment status based on actual data
            if 'fulfill_rate' in product_analysis.columns and 'gap_quantity' in product_analysis.columns:
                def determine_fulfillment_status(row):
                    if pd.isna(row['fulfill_rate']) or pd.isna(row['gap_quantity']):
                        return 'Unknown'
                    elif row['gap_quantity'] <= 0:
                        return 'Can Fulfill All'
                    elif row['fulfill_rate'] == 0:
                        return 'Out of Stock'
                    elif row['fulfill_rate'] < 100:
                        return 'Can Fulfill Partial'
                    else:
                        return 'Can Fulfill All'
                
                product_analysis['fulfillment_status'] = product_analysis.apply(determine_fulfillment_status, axis=1)
            
            # Clean up NaN values in numeric columns
            numeric_columns = ['fulfill_rate', 'gap_quantity', 'total_inventory', 
                            'preferred_warehouse_inventory', 'gap_percentage',
                            'avg_demand_percentage', 'product_total_demand']
            
            for col in numeric_columns:
                if col in product_analysis.columns:
                    product_analysis[col] = product_analysis[col].fillna(0)
            
            logger.info(f"Calculated product demand analysis for {len(product_analysis)} products")
            return product_analysis
            
        except Exception as e:
            logger.error(f"Error calculating product demand from dataframe: {e}")
            return pd.DataFrame()

    # All other methods remain the same (get_customs_clearance_summary, get_customs_clearance_schedule, etc.)
    # These methods don't need changes for the brand filter and exclude functionality
    
    def get_customs_clearance_summary(self, weeks_ahead=4):
        """Get summary of customs clearance deliveries (EPE + Foreign)"""
        try:
            query = text("""
            SELECT 
                COUNT(DISTINCT CASE WHEN is_epe_company = 'Yes' THEN delivery_id END) as epe_deliveries,
                COUNT(DISTINCT CASE WHEN customer_country_code != legal_entity_country_code THEN delivery_id END) as foreign_deliveries,
                COUNT(DISTINCT CASE WHEN customer_country_code != legal_entity_country_code THEN customer_country_name END) as countries
            FROM delivery_full_view
            WHERE etd >= CURDATE()
                AND etd <= DATE_ADD(CURDATE(), INTERVAL :weeks WEEK)
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
                AND (is_epe_company = 'Yes' OR customer_country_code != legal_entity_country_code)
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query, {'weeks': weeks_ahead}).fetchone()
                
            return pd.DataFrame([{
                'epe_deliveries': result[0] or 0,
                'foreign_deliveries': result[1] or 0,
                'countries': result[2] or 0
            }])
            
        except Exception as e:
            logger.error(f"Error getting customs clearance summary: {e}")
            return pd.DataFrame()

    def get_customs_clearance_schedule(self, weeks_ahead=4):
        """Get customs clearance schedule for EPE and Foreign customers"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT DISTINCT
                DATE(etd) as delivery_date,
                etd,
                customer,
                customer_code,
                customer_street,
                customer_state_province,
                customer_country_code,
                customer_country_name,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_code,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                total_instock_all_warehouses,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                legal_entity_code,
                legal_entity_state_province,
                legal_entity_country_code,
                legal_entity_country_name,
                created_by_name,
                created_date,
                -- Calculate customs type
                CASE 
                    WHEN is_epe_company = 'Yes' THEN 'EPE'
                    WHEN customer_country_code != legal_entity_country_code THEN 'Foreign'
                    ELSE 'Domestic'
                END as customs_type,
                -- EPE location info
                CASE 
                    WHEN is_epe_company = 'Yes' THEN 
                        CONCAT(recipient_state_province, ' - ', recipient_company)
                    ELSE NULL
                END as epe_location
            FROM delivery_full_view
            WHERE etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
                AND (
                    is_epe_company = 'Yes' 
                    OR customer_country_code != legal_entity_country_code
                )
            ORDER BY 
                customs_type,
                CASE 
                    WHEN is_epe_company = 'Yes' THEN recipient_state_province
                    ELSE customer_country_name
                END,
                delivery_date,
                customer,
                delivery_id,
                sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'today': today,
                    'end_date': end_date
                })
            
            # Debug: Log columns
            logger.info(f"Columns retrieved from customs query: {df.columns.tolist()}")
            
            # Check for duplicate columns
            if not df.empty:
                duplicate_cols = df.columns[df.columns.duplicated()].tolist()
                if duplicate_cols:
                    logger.warning(f"Duplicate columns found in customs clearance data: {duplicate_cols}")
                    # Remove duplicates
                    df = df.loc[:, ~df.columns.duplicated()]
                
                # Add total_quantity as alias for remaining_quantity_to_deliver
                df['total_quantity'] = df['remaining_quantity_to_deliver']
                
                # Log summary
                epe_count = df[df['customs_type'] == 'EPE']['delivery_id'].nunique()
                foreign_count = df[df['customs_type'] == 'Foreign']['delivery_id'].nunique()
                logger.info(f"Loaded {epe_count} EPE and {foreign_count} Foreign deliveries for customs clearance")
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting customs clearance schedule: {e}")
            return pd.DataFrame()

    def get_customs_clearance_by_type(self, customs_type='EPE'):
        """Get customs clearance data filtered by type (EPE or Foreign)"""
        try:
            df = self.get_customs_clearance_schedule()
            
            if df.empty:
                return pd.DataFrame()
            
            # Filter by customs type
            if customs_type == 'EPE':
                filtered_df = df[df['customs_type'] == 'EPE'].copy()
            elif customs_type == 'Foreign':
                filtered_df = df[df['customs_type'] == 'Foreign'].copy()
            else:
                filtered_df = df.copy()
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Error filtering customs clearance by type: {e}")
            return pd.DataFrame()

    def get_customs_country_summary(self, weeks_ahead=4):
        """Get summary of foreign deliveries by country"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT 
                customer_country_name as country,
                customer_country_code as country_code,
                COUNT(DISTINCT delivery_id) as deliveries,
                COUNT(DISTINCT customer) as customers,
                SUM(remaining_quantity_to_deliver) as total_quantity,
                COUNT(DISTINCT product_id) as products,
                MIN(etd) as first_delivery,
                MAX(etd) as last_delivery
            FROM delivery_full_view
            WHERE etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
                AND customer_country_code != legal_entity_country_code
            GROUP BY customer_country_name, customer_country_code
            ORDER BY deliveries DESC, country
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'today': today,
                    'end_date': end_date
                })
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting customs country summary: {e}")
            return pd.DataFrame()

    def get_epe_location_summary(self, weeks_ahead=4):
        """Get summary of EPE deliveries by location/industrial zone"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT 
                recipient_state_province as location,
                COUNT(DISTINCT delivery_id) as deliveries,
                COUNT(DISTINCT customer) as customers,
                COUNT(DISTINCT recipient_company) as epe_companies,
                SUM(remaining_quantity_to_deliver) as total_quantity,
                COUNT(DISTINCT product_id) as products,
                MIN(etd) as first_delivery,
                MAX(etd) as last_delivery
            FROM delivery_full_view
            WHERE etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
                AND is_epe_company = 'Yes'
            GROUP BY recipient_state_province
            ORDER BY deliveries DESC, location
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'today': today,
                    'end_date': end_date
                })
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting EPE location summary: {e}")
            return pd.DataFrame()
            
    def get_customer_deliveries(self, customer_name, weeks_ahead=4):
        """Get delivery schedule for a specific customer"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT 
                DATE(etd) as delivery_date,
                customer,
                customer_code,
                customer_contact,
                customer_contact_email,
                customer_contact_phone,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                created_by_name,
                created_date
            FROM delivery_full_view
            WHERE customer = :customer_name
                AND etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
            ORDER BY delivery_date, recipient_company, delivery_id, sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'customer_name': customer_name,
                    'today': today,
                    'end_date': end_date
                })
            
            # Add total_quantity alias
            if not df.empty:
                df['total_quantity'] = df['remaining_quantity_to_deliver']
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting customer deliveries: {e}")
            return pd.DataFrame()

    def get_all_deliveries_summary(self, weeks_ahead=4):
        """Get all deliveries summary for custom recipients"""
        try:
            today = datetime.now().date()
            end_date = today + timedelta(weeks=weeks_ahead)
            
            query = text("""
            SELECT 
                DATE(etd) as delivery_date,
                customer,
                customer_code,
                customer_contact,
                customer_contact_email,
                customer_contact_phone,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                created_by_name,
                created_date
            FROM delivery_full_view
            WHERE etd >= :today
                AND etd <= :end_date
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
            ORDER BY delivery_date, customer, recipient_company, delivery_id, sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={
                    'today': today,
                    'end_date': end_date
                })
            
            # Add total_quantity alias
            if not df.empty:
                df['total_quantity'] = df['remaining_quantity_to_deliver']
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting all deliveries summary: {e}")
            return pd.DataFrame()

    def get_all_urgent_deliveries(self):
        """Get all urgent deliveries (overdue and due today) for custom recipients"""
        try:
            query = text("""
            SELECT 
                DATE(etd) as delivery_date,
                customer,
                customer_code,
                customer_contact,
                customer_contact_email,
                customer_contact_phone,
                recipient_company,
                recipient_company_code,
                recipient_contact,
                recipient_contact_email,
                recipient_contact_phone,
                recipient_address,
                recipient_state_province,
                recipient_country_name,
                delivery_id,
                dn_number,
                sto_dr_line_id,
                oc_number,
                oc_line_id,
                product_pn,
                product_id,
                pt_code,
                package_size,
                brand,
                standard_quantity,
                selling_quantity,
                uom_conversion,
                remaining_quantity_to_deliver,
                total_instock_at_preferred_warehouse,
                total_instock_all_warehouses,
                gap_quantity,
                product_gap_quantity,
                product_total_remaining_demand,
                product_fulfill_rate_percent,
                delivery_demand_percentage,
                shipment_status,
                shipment_status_vn,
                fulfillment_status,
                product_fulfillment_status,
                delivery_timeline_status,
                days_overdue,
                preferred_warehouse,
                is_epe_company,
                legal_entity,
                created_by_name,
                created_date
            FROM delivery_full_view
            WHERE delivery_timeline_status IN ('Overdue', 'Due Today')
                AND remaining_quantity_to_deliver > 0
                AND shipment_status NOT IN ('DELIVERED', 'COMPLETED')
            ORDER BY 
                delivery_timeline_status DESC,
                days_overdue DESC,
                delivery_date,
                customer,
                delivery_id,
                sto_dr_line_id
            """)
            
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            
            # Add total_quantity alias
            if not df.empty:
                df['total_quantity'] = df['remaining_quantity_to_deliver']
                
                overdue_count = df[df['delivery_timeline_status'] == 'Overdue']['delivery_id'].nunique()
                due_today_count = df[df['delivery_timeline_status'] == 'Due Today']['delivery_id'].nunique()
                logger.info(f"Loaded {overdue_count} overdue and {due_today_count} due today deliveries for all customers")
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting all urgent deliveries: {e}")
            return pd.DataFrame()