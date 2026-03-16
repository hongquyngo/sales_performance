# utils/delivery_schedule/email_sender.py - Email sending module

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import pandas as pd
from datetime import datetime, timedelta
import logging
import io
import os
from .calendar_utils import CalendarEventGenerator
from ..config import OUTBOUND_EMAIL_CONFIG

logger = logging.getLogger(__name__)


class EmailSender:
    """Handle email notifications for delivery schedules"""
    
    def __init__(self, smtp_host=None, smtp_port=None):
        # Use config V3 (OUTBOUND_EMAIL_CONFIG has sender, password, host, port)
        self.smtp_host = smtp_host or OUTBOUND_EMAIL_CONFIG.get("host", "smtp.gmail.com")
        self.smtp_port = smtp_port or OUTBOUND_EMAIL_CONFIG.get("port", 587)
        self.sender_email = OUTBOUND_EMAIL_CONFIG.get("sender") or os.getenv("EMAIL_SENDER", "outbound@prostech.vn")
        self.sender_password = OUTBOUND_EMAIL_CONFIG.get("password") or os.getenv("EMAIL_PASSWORD", "")
        
        # Log configuration
        logger.info(f"Email sender initialized with: {self.sender_email} via {self.smtp_host}:{self.smtp_port}")
    
    def create_overdue_alerts_html(self, delivery_df, sales_name, contact_name=None):
        """Create HTML content for overdue alerts email"""
        
        # Ensure delivery_date is datetime
        delivery_df['delivery_date'] = pd.to_datetime(delivery_df['delivery_date'])
        
        # Separate overdue and due today
        overdue_df = delivery_df[delivery_df['delivery_timeline_status'] == 'Overdue'].copy()
        due_today_df = delivery_df[delivery_df['delivery_timeline_status'] == 'Due Today'].copy()
        
        # Calculate summary statistics
        total_overdue = overdue_df['delivery_id'].nunique() if not overdue_df.empty else 0
        total_due_today = due_today_df['delivery_id'].nunique() if not due_today_df.empty else 0
        max_days_overdue = overdue_df['days_overdue'].max() if not overdue_df.empty and 'days_overdue' in overdue_df.columns else 0
        
        # Out of stock products
        out_of_stock_products = 0
        if 'product_fulfillment_status' in delivery_df.columns and 'product_id' in delivery_df.columns:
            out_of_stock_products = delivery_df[delivery_df['product_fulfillment_status'] == 'Out of Stock']['product_id'].nunique()
        
        # Determine greeting
        if contact_name and contact_name != 'Unknown Contact':
            greeting = f"Dear {contact_name},"
        else:
            greeting = f"Dear {sales_name},"
        
        # Start HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .header {{
                    background-color: #d32f2f;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                }}
                .alert-box {{
                    background-color: #ffebee;
                    border: 2px solid #ef5350;
                    border-radius: 5px;
                    padding: 15px;
                    margin: 20px 0;
                }}
                .summary-grid {{
                    display: table;
                    width: 100%;
                    margin: 20px 0;
                }}
                .summary-item {{
                    display: table-cell;
                    text-align: center;
                    padding: 10px;
                }}
                .metric-value {{
                    font-size: 36px;
                    font-weight: bold;
                    color: #d32f2f;
                }}
                .metric-label {{
                    font-size: 14px;
                    color: #666;
                    margin-top: 5px;
                }}
                .section-header {{
                    background-color: #f5f5f5;
                    padding: 10px;
                    margin: 20px 0 10px 0;
                    border-left: 4px solid #d32f2f;
                    font-weight: bold;
                    font-size: 18px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                .overdue-row {{
                    background-color: #ffcccb;
                }}
                .due-today-row {{
                    background-color: #ffe4b5;
                }}
                .out-of-stock {{
                    color: #d32f2f;
                    font-weight: bold;
                }}
                .days-overdue {{
                    color: #d32f2f;
                    font-weight: bold;
                    font-size: 16px;
                }}
                .action-box {{
                    background-color: #e3f2fd;
                    border: 1px solid #2196f3;
                    border-radius: 5px;
                    padding: 15px;
                    margin: 20px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding: 20px;
                    background-color: #f8f9fa;
                    text-align: center;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚨 URGENT DELIVERY ALERT</h1>
                <p>Immediate Action Required</p>
            </div>
            
            <div class="content">
                <p>{greeting}</p>
                
                <div class="alert-box">
                    <strong>⚠️ CRITICAL ALERT:</strong> You have deliveries that require immediate attention. 
                    Please review the details below and take necessary action to avoid further delays.
                </div>
                
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="metric-value">{total_overdue}</div>
                        <div class="metric-label">Overdue Deliveries</div>
                    </div>
                    <div class="summary-item">
                        <div class="metric-value">{total_due_today}</div>
                        <div class="metric-label">Due Today</div>
                    </div>
                    <div class="summary-item">
                        <div class="metric-value">{int(max_days_overdue)}</div>
                        <div class="metric-label">Max Days Overdue</div>
                    </div>
                    <div class="summary-item">
                        <div class="metric-value">{out_of_stock_products}</div>
                        <div class="metric-label">Out of Stock Products</div>
                    </div>
                </div>
        """
        
        # Overdue Section
        if not overdue_df.empty:
            html += """
                <div class="section-header">🔴 OVERDUE DELIVERIES</div>
                <p>These deliveries are past their expected delivery date and need immediate attention:</p>
                <table>
                    <tr>
                        <th width="80">Days Overdue</th>
                        <th width="100">Delivery Date</th>
                        <th width="150">Customer</th>
                        <th width="150">Ship To</th>
                        <th width="80">PT Code</th>
                        <th width="120">Product</th>
                        <th width="80">Quantity</th>
                        <th width="100">Fulfillment</th>
                        <th width="120">DN Number</th>
                    </tr>
            """
            
            # Group and sort overdue deliveries
            overdue_display = overdue_df.sort_values(['days_overdue', 'delivery_date'], ascending=[False, True])
            
            for _, row in overdue_display.iterrows():
                days_overdue = int(row['days_overdue']) if pd.notna(row['days_overdue']) else 0
                fulfillment_status = row.get('product_fulfillment_status', row.get('fulfillment_status', 'Unknown'))
                fulfillment_class = 'out-of-stock' if fulfillment_status == 'Out of Stock' else ''
                
                html += f"""
                    <tr class="overdue-row">
                        <td class="days-overdue">{days_overdue} days</td>
                        <td>{row['delivery_date'].strftime('%Y-%m-%d')}</td>
                        <td>{row['customer']}</td>
                        <td>{row['recipient_company']}</td>
                        <td>{row['pt_code']}</td>
                        <td>{row['product_pn']}</td>
                        <td>{row['remaining_quantity_to_deliver']:,.0f}</td>
                        <td class="{fulfillment_class}">{fulfillment_status}</td>
                        <td>{row['dn_number']}</td>
                    </tr>
                """
            
            html += "</table>"
        
        # Due Today Section
        if not due_today_df.empty:
            html += """
                <div class="section-header">🟡 DUE TODAY</div>
                <p>These deliveries are scheduled for today and should be prioritized:</p>
                <table>
                    <tr>
                        <th width="100">Delivery Date</th>
                        <th width="150">Customer</th>
                        <th width="150">Ship To</th>
                        <th width="80">PT Code</th>
                        <th width="120">Product</th>
                        <th width="80">Quantity</th>
                        <th width="100">Fulfillment</th>
                        <th width="120">DN Number</th>
                    </tr>
            """
            
            # Sort by fulfillment status (out of stock first)
            due_today_display = due_today_df.sort_values(['product_fulfillment_status', 'customer'])
            
            for _, row in due_today_display.iterrows():
                fulfillment_status = row.get('product_fulfillment_status', row.get('fulfillment_status', 'Unknown'))
                fulfillment_class = 'out-of-stock' if fulfillment_status == 'Out of Stock' else ''
                
                html += f"""
                    <tr class="due-today-row">
                        <td>{row['delivery_date'].strftime('%Y-%m-%d')}</td>
                        <td>{row['customer']}</td>
                        <td>{row['recipient_company']}</td>
                        <td>{row['pt_code']}</td>
                        <td>{row['product_pn']}</td>
                        <td>{row['remaining_quantity_to_deliver']:,.0f}</td>
                        <td class="{fulfillment_class}">{fulfillment_status}</td>
                        <td>{row['dn_number']}</td>
                    </tr>
                """
            
            html += "</table>"
        
        # Action Items
        html += """
            <div class="action-box">
                <h3>📋 Required Actions:</h3>
                <ol>
                    <li><strong>Contact Customers:</strong> Inform customers about delivery delays and provide updated ETAs</li>
                    <li><strong>Coordinate with Warehouse:</strong> Check inventory availability for out-of-stock items</li>
                    <li><strong>Update Delivery Status:</strong> Ensure all delivery statuses are current in the system</li>
                    <li><strong>Escalate if Needed:</strong> For deliveries overdue by 5+ days, escalate to management</li>
                </ol>
                
                <p><strong>Logistics Team Contact:</strong><br>
                📧 Email: outbound@prostech.vn<br>
                📞 Phone: +84 33 476273</p>
            </div>
            
            <div class="footer">
                <p>This is an automated urgent alert from Outbound Logistics System</p>
                <p>Please take immediate action on the items listed above</p>
                <p>For questions, contact: <a href="mailto:outbound@prostech.vn">outbound@prostech.vn</a></p>
            </div>
        </div>
        </body>
        </html>
        """
        
        return html
    
    def create_delivery_schedule_html(self, delivery_df, recipient_name, weeks_ahead=4, contact_name=None):
        """Create HTML content for delivery schedule email with DN Number and Province"""
        
        # Ensure delivery_date is datetime
        delivery_df['delivery_date'] = pd.to_datetime(delivery_df['delivery_date'])
        
        # Calculate week information
        delivery_df['week_start'] = delivery_df['delivery_date'] - pd.to_timedelta(delivery_df['delivery_date'].dt.dayofweek, unit='D')
        delivery_df['week_end'] = delivery_df['week_start'] + timedelta(days=6)
        delivery_df['week_key'] = delivery_df['week_start'].dt.strftime('%Y-%m-%d')
        delivery_df['week'] = delivery_df['delivery_date'].dt.isocalendar().week
        delivery_df['year'] = delivery_df['delivery_date'].dt.year
        
        # Calculate summary statistics
        out_of_stock_products = 0
        avg_fulfill_rate = 100.0
        
        if 'product_fulfillment_status' in delivery_df.columns and 'product_id' in delivery_df.columns:
            out_of_stock_products = delivery_df[delivery_df['product_fulfillment_status'] == 'Out of Stock']['product_id'].nunique()
        
        if 'product_fulfill_rate_percent' in delivery_df.columns and 'product_id' in delivery_df.columns:
            avg_fulfill_rate = delivery_df.groupby('product_id')['product_fulfill_rate_percent'].first().mean()
        
        # Format weeks text
        week_text = f"{weeks_ahead} Week" if weeks_ahead == 1 else f"{weeks_ahead} Weeks"
        
        # Determine the greeting based on whether we have a contact name
        if contact_name and contact_name != 'Unknown Contact':
            greeting = f"Dear {contact_name},"
        else:
            greeting = f"Dear {recipient_name},"
        
        # Start HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .header {{
                    background-color: #1f77b4;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                }}
                .week-section {{
                    margin-bottom: 30px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    padding: 15px;
                }}
                .week-header {{
                    background-color: #f0f2f6;
                    padding: 10px;
                    margin: -15px -15px 15px -15px;
                    border-radius: 5px 5px 0 0;
                    font-weight: bold;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                .urgent {{
                    color: #d32f2f;
                    font-weight: bold;
                }}
                .overdue {{
                    background-color: #ffcccb;
                    font-weight: bold;
                }}
                .warning {{
                    background-color: #fff3cd;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 10px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding: 20px;
                    background-color: #f8f9fa;
                    text-align: center;
                    font-size: 12px;
                    color: #666;
                }}
                .metric-box {{
                    display: inline-block;
                    background-color: #f0f2f6;
                    padding: 15px;
                    margin: 10px;
                    border-radius: 5px;
                    text-align: center;
                }}
                .metric-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #1f77b4;
                }}
                .metric-label {{
                    font-size: 12px;
                    color: #666;
                    margin-top: 5px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📦 Delivery Schedule Notification</h1>
                <p>Your Upcoming Delivery Plan - Next {week_text}</p>
            </div>
            
            <div class="content">
                <p>{greeting}</p>
                <p>Please find below your upcoming delivery schedule for the next {weeks_ahead} week{'s' if weeks_ahead != 1 else ''}. 
                Make sure to coordinate with customers for smooth delivery operations.</p>
                
                <div class="summary">
                    <h3>📊 Summary</h3>
                    <div style="text-align: center;">
                        <div class="metric-box">
                            <div class="metric-value">{delivery_df.groupby(['delivery_date', 'customer', 'recipient_company']).ngroups}</div>
                            <div class="metric-label">Total Deliveries</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-value">{delivery_df['product_id'].nunique() if 'product_id' in delivery_df.columns else delivery_df['product_pn'].nunique()}</div>
                            <div class="metric-label">Product Types</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-value">{delivery_df['remaining_quantity_to_deliver'].sum():,.0f}</div>
                            <div class="metric-label">Total Quantity</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-value">{avg_fulfill_rate:.1f}%</div>
                            <div class="metric-label">Avg Fulfillment Rate</div>
                        </div>
                    </div>
                </div>
        """
        
        # Add alerts if any out of stock products
        if out_of_stock_products > 0:
            html += f"""
                <div class="warning">
                    <strong>⚠️ Attention Required:</strong><br>
                    • {out_of_stock_products} products are out of stock<br>
                    Please coordinate with the logistics team to resolve these issues.
                </div>
            """
        
        # Group by week and create sections
        for week_key, week_df in delivery_df.groupby('week_key', sort=True):
            week_start = week_df['week_start'].iloc[0]
            week_end = week_df['week_end'].iloc[0]
            week_number = week_df['week'].iloc[0]
            
            # Calculate totals for this week
            week_unique_deliveries = week_df.groupby(['delivery_date', 'customer', 'recipient_company']).ngroups
            week_unique_products = week_df['product_id'].nunique()
            week_total_qty = week_df['remaining_quantity_to_deliver'].sum()
            
            html += f"""
                <div class="week-section">
                    <div class="week-header">
                        Week {week_number} ({week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')})
                        <span style="float: right; font-size: 14px;">
                            {week_unique_deliveries} deliveries | {week_unique_products} products | {week_total_qty:,.0f} units
                        </span>
                    </div>
            """
            
            html += """
                    <table>
                        <tr>
                            <th style="width: 80px;">Date</th>
                            <th style="width: 100px;">DN Number</th>
                            <th style="width: 150px;">Customer</th>
                            <th style="width: 150px;">Ship To</th>
                            <th style="width: 100px;">Province</th>
                            <th style="width: 80px;">PT Code</th>
                            <th style="width: 120px;">Product</th>
                            <th style="width: 60px;">Qty</th>
                            <th style="width: 90px;">Fulfillment</th>
                        </tr>
            """
            
            # Group by delivery for display
            if 'product_id' in week_df.columns:
                group_cols = ['delivery_date', 'dn_number', 'customer', 'recipient_company', 
                            'recipient_state_province', 'product_id', 'pt_code', 'product_pn']
            else:
                group_cols = ['delivery_date', 'dn_number', 'customer', 'recipient_company', 
                            'recipient_state_province', 'pt_code', 'product_pn']
            
            # Create aggregation
            agg_dict = {
                'remaining_quantity_to_deliver': 'sum'
            }
            
            if 'product_fulfillment_status' in week_df.columns:
                agg_dict['product_fulfillment_status'] = 'first'
            
            display_group = week_df.groupby(group_cols, as_index=False).agg(agg_dict)
            
            # Sort by date and DN number
            display_group = display_group.sort_values(['delivery_date', 'dn_number'])
            
            # Add rows to table
            for _, row in display_group.iterrows():
                # Product fulfillment status
                product_status = row.get('product_fulfillment_status', 'Unknown')
                status_class = 'urgent' if product_status in ['Out of Stock', 'Can Fulfill Partial'] else ''
                
                # Format province name
                province = row['recipient_state_province'] if pd.notna(row['recipient_state_province']) else ''
                
                html += f"""
                        <tr>
                            <td>{row['delivery_date'].strftime('%b %d')}</td>
                            <td>{row['dn_number']}</td>
                            <td>{row['customer']}</td>
                            <td>{row['recipient_company']}</td>
                            <td>{province}</td>
                            <td>{row['pt_code']}</td>
                            <td>{row['product_pn']}</td>
                            <td>{row['remaining_quantity_to_deliver']:,.0f}</td>
                            <td class="{status_class}">{product_status}</td>
                        </tr>
                """
            
            html += """
                    </table>
                </div>
            """
        
        # Add legend
        html += """
            <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 5px;">
                <h4>Fulfillment Status:</h4>
                <p>• <strong>Can Fulfill All:</strong> Sufficient inventory for all deliveries<br>
                • <strong>Can Fulfill Partial:</strong> Limited inventory available<br>
                • <strong>Out of Stock:</strong> No inventory available</p>
            </div>
        """
        
        # Add footer
        html += """
                <div class="footer">
                    <p>This is an automated email from Outbound Logistics System</p>
                    <p>For questions, please contact: <a href="mailto:outbound@prostech.vn">outbound@prostech.vn</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

    def send_delivery_schedule_email(self, recipient_email, recipient_name, delivery_df, 
                                cc_emails=None, notification_type="📅 Delivery Schedule", 
                                weeks_ahead=4, contact_name=None):
        """Send delivery schedule email with enhanced content"""
        try:
            # Check email configuration
            if not self.sender_email or not self.sender_password:
                logger.error("Email configuration missing. Please set EMAIL_SENDER and EMAIL_PASSWORD.")
                return False, "Email configuration missing. Please check environment variables."
            
            # Remove duplicate columns
            delivery_df = delivery_df.loc[:, ~delivery_df.columns.duplicated()]
            
            # Create message
            msg = MIMEMultipart('alternative')
            
            # Set subject based on notification type with dynamic weeks
            if notification_type == "🚨 Overdue Alerts":
                overdue_count = delivery_df[delivery_df['delivery_timeline_status'] == 'Overdue']['delivery_id'].nunique()
                due_today_count = delivery_df[delivery_df['delivery_timeline_status'] == 'Due Today']['delivery_id'].nunique()
                # Include contact name in urgent subject if available
                if contact_name and contact_name != 'Unknown Contact':
                    msg['Subject'] = f"🚨 URGENT: {overdue_count} Overdue & {due_today_count} Due Today Deliveries - {recipient_name} (Attn: {contact_name})"
                else:
                    msg['Subject'] = f"🚨 URGENT: {overdue_count} Overdue & {due_today_count} Due Today Deliveries - {recipient_name}"
            else:
                # Dynamic subject with weeks_ahead
                week_text = f"{weeks_ahead} Week" if weeks_ahead == 1 else f"{weeks_ahead} Weeks"
                # Include contact name in subject if available
                if contact_name and contact_name != 'Unknown Contact':
                    msg['Subject'] = f"Delivery Schedule - Next {week_text} - {recipient_name} (Attn: {contact_name})"
                else:
                    msg['Subject'] = f"Delivery Schedule - Next {week_text} - {recipient_name}"
            
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            
            # Create HTML content based on notification type
            if notification_type == "🚨 Overdue Alerts":
                html_content = self.create_overdue_alerts_html(delivery_df, recipient_name, contact_name)
            else:
                html_content = self.create_delivery_schedule_html(delivery_df, recipient_name, weeks_ahead, contact_name)
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Create Excel attachment
            excel_data = self.create_excel_attachment(delivery_df, notification_type)
            excel_part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            excel_part.set_payload(excel_data.read())
            encoders.encode_base64(excel_part)
            
            # Set filename based on notification type and recipient
            if notification_type == "🚨 Overdue Alerts":
                if contact_name and contact_name != 'Unknown Contact':
                    filename = f"urgent_deliveries_{recipient_name}_{contact_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                else:
                    filename = f"urgent_deliveries_{recipient_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            else:
                if contact_name and contact_name != 'Unknown Contact':
                    filename = f"delivery_schedule_{recipient_name}_{contact_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
                else:
                    filename = f"delivery_schedule_{recipient_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            
            # Clean filename
            filename = filename.replace(' ', '_').replace('/', '_').replace('\\', '_')
            
            excel_part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )
            msg.attach(excel_part)
            
            # Create ICS calendar attachment (only for delivery schedule)
            if notification_type == "📅 Delivery Schedule":
                try:
                    calendar_gen = CalendarEventGenerator()
                    ics_content = calendar_gen.create_ics_content(recipient_name, delivery_df, self.sender_email)
                    
                    if ics_content:
                        ics_part = MIMEBase('text', 'calendar')
                        ics_part.set_payload(ics_content.encode('utf-8'))
                        encoders.encode_base64(ics_part)
                        
                        # Include contact name in calendar filename if available
                        if contact_name and contact_name != 'Unknown Contact':
                            cal_filename = f"delivery_schedule_{recipient_name}_{contact_name}_{datetime.now().strftime('%Y%m%d')}.ics"
                        else:
                            cal_filename = f"delivery_schedule_{recipient_name}_{datetime.now().strftime('%Y%m%d')}.ics"
                        
                        cal_filename = cal_filename.replace(' ', '_').replace('/', '_').replace('\\', '_')
                        
                        ics_part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{cal_filename}"'
                        )
                        msg.attach(ics_part)
                except Exception as e:
                    logger.warning(f"Error creating calendar attachment: {e}")
            
            # Send email
            logger.info(f"Attempting to send {notification_type} email to {recipient_email}...")
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                
                recipients = [recipient_email]
                if cc_emails:
                    recipients.extend(cc_emails)
                
                server.sendmail(self.sender_email, recipients, msg.as_string())
            
            logger.info(f"Email sent successfully to {recipient_email}")
            return True, "Email sent successfully"
            
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return False, str(e)

    def create_excel_attachment(self, delivery_df, notification_type="📅 Delivery Schedule"):
        """Create Excel file as attachment with enhanced information"""
        output = io.BytesIO()
        
        # Create a copy for Excel export - NO AGGREGATION, show all line items
        excel_df = delivery_df.copy()
        
        # Format date columns for Excel
        date_columns = ['delivery_date', 'created_date', 'delivered_date', 'dispatched_date', 'sto_etd_date', 'oc_date']
        for col in date_columns:
            if col in excel_df.columns:
                excel_df[col] = pd.to_datetime(excel_df[col]).dt.strftime('%Y-%m-%d')
        
        # Drop internal calculation columns if they exist
        columns_to_drop = ['week_start', 'week_end', 'week_key', 'week', 'year', 'total_quantity']
        excel_df = excel_df.drop(columns=[col for col in columns_to_drop if col in excel_df.columns])
        
        # Remove duplicate columns before processing
        excel_df = excel_df.loc[:, ~excel_df.columns.duplicated()]
        
        # Select and order important columns for better readability
        important_columns = [
            'delivery_date',
            'delivery_timeline_status',
            'days_overdue',
            'dn_number',
            'customer',
            'customer_code',
            'recipient_company',
            'recipient_company_code',
            'recipient_contact',
            'recipient_address',
            'recipient_state_province',
            'recipient_country_name',
            'product_pn',
            'product_id',
            'pt_code',
            'package_size',
            'standard_quantity',
            'remaining_quantity_to_deliver',
            'product_total_remaining_demand',
            'delivery_demand_percentage',
            'product_gap_quantity',
            'product_fulfill_rate_percent',
            'fulfillment_status',
            'product_fulfillment_status',
            'shipment_status',
            'shipment_status_vn',
            'oc_number',
            'oc_line_id',
            'preferred_warehouse',
            'total_instock_at_preferred_warehouse',
            'total_instock_all_warehouses',
            'created_by_name',
            'is_epe_company'
        ]
        
        # Filter to only include columns that exist
        available_columns = [col for col in important_columns if col in excel_df.columns]
        
        # Add any remaining columns not in the important list
        remaining_columns = [col for col in excel_df.columns if col not in available_columns]
        final_columns = available_columns + remaining_columns
        
        # Remove duplicates from final columns list
        final_columns = list(dict.fromkeys(final_columns))
        
        # Reorder dataframe
        excel_df = excel_df[final_columns]
        
        # Sort by delivery date and customer for better organization
        sort_columns = ['delivery_date', 'customer', 'dn_number', 'oc_line_id']
        sort_columns = [col for col in sort_columns if col in excel_df.columns]
        if sort_columns:
            excel_df = excel_df.sort_values(sort_columns)
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            try:
                # For Overdue Alerts, create different sheets
                if notification_type == "🚨 Overdue Alerts":
                    # Separate overdue and due today
                    overdue_df = excel_df[excel_df['delivery_timeline_status'] == 'Overdue'].copy()
                    due_today_df = excel_df[excel_df['delivery_timeline_status'] == 'Due Today'].copy()
                    
                    # Write overdue sheet
                    if not overdue_df.empty:
                        overdue_df = overdue_df.sort_values('days_overdue', ascending=False)
                        overdue_df.to_excel(writer, sheet_name='Overdue Deliveries', index=False)
                    
                    # Write due today sheet
                    if not due_today_df.empty:
                        due_today_df.to_excel(writer, sheet_name='Due Today', index=False)
                    
                    # Create summary sheet
                    summary_df = self._create_urgent_summary_sheet(delivery_df)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                else:
                    # Regular delivery schedule sheets
                    excel_df.to_excel(writer, sheet_name='Line Items Detail', index=False)
                    
                    # Create summary sheet
                    summary_df = self._create_summary_sheet(delivery_df)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                    
                    # Create product analysis sheet (only if columns exist)
                    if 'product_gap_quantity' in delivery_df.columns:
                        try:
                            product_analysis_df = self._create_product_analysis_sheet(delivery_df)
                            product_analysis_df.to_excel(writer, sheet_name='Product Analysis', index=False)
                        except Exception as e:
                            logger.warning(f"Could not create Product Analysis sheet: {e}")
                
                # Get workbook and apply formatting
                workbook = writer.book
                
                # Define formats
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#1f77b4' if notification_type == "📅 Delivery Schedule" else '#d32f2f',
                    'font_color': 'white',
                    'border': 1,
                    'text_wrap': True,
                    'valign': 'vcenter'
                })
                
                date_format = workbook.add_format({
                    'num_format': 'yyyy-mm-dd',
                    'border': 1
                })
                
                number_format = workbook.add_format({
                    'num_format': '#,##0',
                    'border': 1
                })
                
                percent_format = workbook.add_format({
                    'num_format': '0.0%',
                    'border': 1
                })
                
                urgent_format = workbook.add_format({
                    'bg_color': '#ffcccb',
                    'border': 1
                })
                
                overdue_format = workbook.add_format({
                    'bg_color': '#ffcccb',
                    'font_color': '#d32f2f',
                    'bold': True,
                    'border': 1
                })
                
                # Apply formatting to all sheets
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    
                    # Set column widths and formatting
                    worksheet.set_column(0, 50, 15)  # Default width
                    
                    # Freeze first row
                    worksheet.freeze_panes(1, 0)
                    
                    # Add filters
                    if sheet_name in ['Line Items Detail', 'Overdue Deliveries', 'Due Today']:
                        last_row = len(excel_df) if sheet_name == 'Line Items Detail' else len(overdue_df) + len(due_today_df)
                        last_col = len(final_columns) - 1
                        worksheet.autofilter(0, 0, last_row, last_col)
                
            except Exception as e:
                logger.error(f"Error creating Excel sheets: {e}")
                raise
        
        output.seek(0)
        return output
    
    def _create_urgent_summary_sheet(self, delivery_df):
        """Create summary sheet for urgent alerts"""
        # Remove duplicate columns first
        delivery_df_clean = delivery_df.loc[:, ~delivery_df.columns.duplicated()]
        
        # Calculate summary by customer and status
        summary_data = []
        
        # Group by customer and timeline status
        for (customer, status), group_df in delivery_df_clean.groupby(['customer', 'delivery_timeline_status']):
            summary_data.append({
                'Customer': customer,
                'Status': status,
                'Deliveries': group_df['delivery_id'].nunique(),
                'Line Items': len(group_df),
                'Total Quantity': group_df['remaining_quantity_to_deliver'].sum(),
                'Max Days Overdue': group_df['days_overdue'].max() if status == 'Overdue' else 0,
                'Out of Stock Products': group_df[group_df['product_fulfillment_status'] == 'Out of Stock']['product_pn'].nunique()
            })
        
        summary_df = pd.DataFrame(summary_data)
        
        # Sort by status (Overdue first) and days overdue
        summary_df['Status_Sort'] = summary_df['Status'].map({'Overdue': 0, 'Due Today': 1})
        summary_df = summary_df.sort_values(['Status_Sort', 'Max Days Overdue'], ascending=[True, False])
        summary_df = summary_df.drop('Status_Sort', axis=1)
        
        return summary_df
    
    def _create_summary_sheet(self, delivery_df):
        """Create summary data for Excel"""
        # Remove duplicate columns first
        delivery_df_clean = delivery_df.loc[:, ~delivery_df.columns.duplicated()]
        
        # Direct grouping - no need to group twice
        agg_dict = {
            'dn_number': lambda x: ', '.join(x.unique()),
            'product_pn': lambda x: len(x.unique()),
            'standard_quantity': 'sum',
            'remaining_quantity_to_deliver': 'sum'
        }
        
        # Add conditional aggregations only if columns exist
        if 'fulfillment_status' in delivery_df_clean.columns:
            agg_dict['fulfillment_status'] = lambda x: 'Mixed' if x.nunique() > 1 else x.iloc[0]
        
        if 'delivery_timeline_status' in delivery_df_clean.columns:
            agg_dict['delivery_timeline_status'] = lambda x: x.iloc[0]
            
        if 'days_overdue' in delivery_df_clean.columns:
            agg_dict['days_overdue'] = 'max'
        
        summary = delivery_df_clean.groupby(['delivery_date', 'customer', 'recipient_company']).agg(agg_dict).reset_index()
        
        # Calculate line items count
        line_items = delivery_df_clean.groupby(['delivery_date', 'customer', 'recipient_company']).size().reset_index(name='line_items_count')
        
        # Merge line items count
        summary = summary.merge(line_items, on=['delivery_date', 'customer', 'recipient_company'])
        
        # Build columns list dynamically
        cols = ['delivery_date', 'customer', 'recipient_company', 'dn_number',
                'line_items_count', 'product_pn', 'standard_quantity', 
                'remaining_quantity_to_deliver']
        
        # Add optional columns only if they exist in summary
        if 'delivery_timeline_status' in summary.columns:
            cols.append('delivery_timeline_status')
        if 'days_overdue' in summary.columns:
            cols.append('days_overdue')
        if 'fulfillment_status' in summary.columns:
            cols.append('fulfillment_status')
        
        # Select only existing columns
        cols = [col for col in cols if col in summary.columns]
        summary = summary[cols]
        
        # Rename columns
        summary.columns = [col.replace('_', ' ').title() for col in summary.columns]
        
        # Sort by delivery date
        summary = summary.sort_values('Delivery Date')
        
        return summary
    
    def _create_product_analysis_sheet(self, delivery_df):
        """Create product analysis sheet for Excel"""
        # Remove duplicate columns first
        delivery_df_clean = delivery_df.loc[:, ~delivery_df.columns.duplicated()]
        
        # Check if product_id exists
        if 'product_id' not in delivery_df_clean.columns:
            return pd.DataFrame()  # Return empty if no product_id
        
        # Group by product for analysis
        product_analysis = delivery_df_clean.groupby(['product_id', 'pt_code', 'product_pn']).agg({
            'delivery_id': 'nunique',
            'remaining_quantity_to_deliver': 'sum',
            'product_total_remaining_demand': 'first',
            'total_instock_all_warehouses': 'first',
            'product_gap_quantity': 'first',
            'product_fulfill_rate_percent': 'first',
            'product_fulfillment_status': 'first'
        }).reset_index()
        
        # Rename columns
        product_analysis.columns = [
            'Product ID',
            'PT Code',
            'Product',
            'Active Deliveries',
            'This Sales Demand',
            'Total Product Demand',
            'Total Inventory',
            'Gap Quantity',
            'Fulfillment Rate %',
            'Fulfillment Status'
        ]
        
        # Sort by gap quantity (descending)
        product_analysis = product_analysis.sort_values('Gap Quantity', ascending=False)
        
        return product_analysis
    
    def send_bulk_delivery_schedules(self, sales_deliveries, progress_callback=None):
        """Send delivery schedules to multiple sales people"""
        results = []
        total = len(sales_deliveries)
        
        for idx, (sales_info, delivery_df) in enumerate(sales_deliveries):
            if progress_callback:
                progress_callback(idx + 1, total, f"Sending to {sales_info['name']}...")
            
            success, message = self.send_delivery_schedule_email(
                sales_info['email'],
                sales_info['name'],
                delivery_df
            )
            
            results.append({
                'sales': sales_info['name'],
                'email': sales_info['email'],
                'success': success,
                'message': message,
                'deliveries': len(delivery_df)
            })
        
        return results
    
    def create_customs_clearance_html(self, delivery_df, weeks_ahead=4):
        """Create HTML content for customs clearance email"""
        
        # Ensure delivery_date is datetime
        delivery_df['delivery_date'] = pd.to_datetime(delivery_df['delivery_date'])
        
        # Separate EPE and Foreign deliveries
        epe_df = delivery_df[delivery_df['customs_type'] == 'EPE'].copy()
        foreign_df = delivery_df[delivery_df['customs_type'] == 'Foreign'].copy()
        
        # Calculate summary statistics
        total_epe_deliveries = epe_df['delivery_id'].nunique() if not epe_df.empty else 0
        total_foreign_deliveries = foreign_df['delivery_id'].nunique() if not foreign_df.empty else 0
        total_countries = foreign_df['customer_country_name'].nunique() if not foreign_df.empty else 0
        total_epe_locations = epe_df['recipient_state_province'].nunique() if not epe_df.empty else 0
        
        total_quantity = delivery_df['remaining_quantity_to_deliver'].sum()
        
        # Start HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .header {{
                    background-color: #00796b;
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .content {{
                    padding: 20px;
                }}
                .summary-section {{
                    background-color: #f5f5f5;
                    border-radius: 5px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .summary-grid {{
                    display: table;
                    width: 100%;
                    margin: 20px 0;
                }}
                .summary-item {{
                    display: table-cell;
                    text-align: center;
                    padding: 10px;
                    border-right: 1px solid #ddd;
                }}
                .summary-item:last-child {{
                    border-right: none;
                }}
                .metric-value {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #00796b;
                }}
                .metric-label {{
                    font-size: 14px;
                    color: #666;
                    margin-top: 5px;
                }}
                .section-header {{
                    background-color: #e0f2f1;
                    padding: 12px;
                    margin: 25px 0 15px 0;
                    border-left: 4px solid #00796b;
                    font-weight: bold;
                    font-size: 18px;
                }}
                .sub-section-header {{
                    background-color: #f5f5f5;
                    padding: 8px;
                    margin: 15px 0 10px 0;
                    border-left: 3px solid #4db6ac;
                    font-weight: bold;
                    font-size: 16px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }}
                th {{
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                .epe-row {{
                    background-color: #e8f5e9;
                }}
                .foreign-row {{
                    background-color: #e3f2fd;
                }}
                .location-tag {{
                    background-color: #4db6ac;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                }}
                .country-tag {{
                    background-color: #2196f3;
                    color: white;
                    padding: 2px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                }}
                .week-summary {{
                    background-color: #f8f9fa;
                    padding: 10px;
                    margin: 10px 0;
                    border-radius: 5px;
                }}
                .footer {{
                    margin-top: 30px;
                    padding: 20px;
                    background-color: #f8f9fa;
                    text-align: center;
                    font-size: 12px;
                    color: #666;
                }}
                .info-box {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeeba;
                    border-radius: 5px;
                    padding: 15px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🛃 Custom Clearance Schedule</h1>
                <p>EPE & Foreign Customer Deliveries - Next {weeks_ahead} Week{'s' if weeks_ahead != 1 else ''}</p>
            </div>
            
            <div class="content">
                <p>Dear Custom Clearance Team,</p>
                <p>Please find below the customs clearance schedule for the next {weeks_ahead} week{'s' if weeks_ahead != 1 else ''}, 
                including Export Processing Enterprise (EPE) deliveries and foreign customer shipments.</p>
                
                <div class="summary-section">
                    <h3>📊 Summary Overview</h3>
                    <div class="summary-grid">
                        <div class="summary-item">
                            <div class="metric-value">{total_epe_deliveries}</div>
                            <div class="metric-label">EPE Deliveries<br>(Xuất khẩu tại chỗ)</div>
                        </div>
                        <div class="summary-item">
                            <div class="metric-value">{total_foreign_deliveries}</div>
                            <div class="metric-label">Foreign Deliveries<br>(Xuất khẩu thông thường)</div>
                        </div>
                        <div class="summary-item">
                            <div class="metric-value">{total_countries}</div>
                            <div class="metric-label">Destination Countries</div>
                        </div>
                        <div class="summary-item">
                            <div class="metric-value">{total_quantity:,.0f}</div>
                            <div class="metric-label">Total Quantity</div>
                        </div>
                    </div>
                </div>
        """
        
        # EPE Section (Xuất khẩu tại chỗ)
        if not epe_df.empty:
            html += """
                <div class="section-header">📦 XUẤT KHẨU TẠI CHỖ (EPE Companies)</div>
                <p>Deliveries to Export Processing Enterprises within Vietnam requiring local export procedures:</p>
            """
            
            # Group EPE by location and week
            epe_df['week_start'] = epe_df['delivery_date'] - pd.to_timedelta(epe_df['delivery_date'].dt.dayofweek, unit='D')
            epe_df['week_number'] = epe_df['delivery_date'].dt.isocalendar().week
            
            # Group by location first
            for location, loc_df in epe_df.groupby('recipient_state_province', sort=True):
                location_deliveries = loc_df['delivery_id'].nunique()
                location_quantity = loc_df['remaining_quantity_to_deliver'].sum()
                
                html += f"""
                    <div class="sub-section-header">
                        <span class="location-tag">{location}</span>
                        <span style="float: right; font-size: 14px; font-weight: normal;">
                            {location_deliveries} deliveries | {location_quantity:,.0f} units
                        </span>
                    </div>
                """
                
                # Then group by week within location
                for week_key, week_df in loc_df.groupby('week_start', sort=True):
                    week_number = week_df['week_number'].iloc[0]
                    week_end = week_key + timedelta(days=6)
                    
                    html += f"""
                        <div class="week-summary">
                            <strong>Week {week_number} ({week_key.strftime('%b %d')} - {week_end.strftime('%b %d')})</strong>
                        </div>
                        <table>
                            <tr>
                                <th width="90">Date</th>
                                <th width="180">EPE Company</th>
                                <th width="150">Customer</th>
                                <th width="100">DN Number</th>
                                <th width="80">PT Code</th>
                                <th width="120">Product</th>
                                <th width="80">Quantity</th>
                            </tr>
                    """
                    
                    # Group by delivery for display
                    display_df = week_df.groupby(['delivery_date', 'recipient_company', 'customer', 
                                                'dn_number', 'product_id', 'pt_code', 'product_pn']).agg({
                        'remaining_quantity_to_deliver': 'sum'
                    }).reset_index()
                    
                    for _, row in display_df.iterrows():
                        html += f"""
                            <tr class="epe-row">
                                <td>{row['delivery_date'].strftime('%b %d')}</td>
                                <td>{row['recipient_company']}</td>
                                <td>{row['customer']}</td>
                                <td>{row['dn_number']}</td>
                                <td>{row['pt_code']}</td>
                                <td>{row['product_pn']}</td>
                                <td>{row['remaining_quantity_to_deliver']:,.0f}</td>
                            </tr>
                        """
                    
                    html += "</table>"
        
        # Foreign Section (Xuất khẩu thông thường)
        if not foreign_df.empty:
            html += """
                <div class="section-header">🌍 XUẤT KHẨU THÔNG THƯỜNG (Foreign Customers)</div>
                <p>International shipments requiring standard export procedures:</p>
            """
            
            # Group Foreign by country and week
            foreign_df['week_start'] = foreign_df['delivery_date'] - pd.to_timedelta(foreign_df['delivery_date'].dt.dayofweek, unit='D')
            foreign_df['week_number'] = foreign_df['delivery_date'].dt.isocalendar().week
            
            # Group by country first
            for country, country_df in foreign_df.groupby('customer_country_name', sort=True):
                country_deliveries = country_df['delivery_id'].nunique()
                country_quantity = country_df['remaining_quantity_to_deliver'].sum()
                
                html += f"""
                    <div class="sub-section-header">
                        <span class="country-tag">{country}</span>
                        <span style="float: right; font-size: 14px; font-weight: normal;">
                            {country_deliveries} deliveries | {country_quantity:,.0f} units
                        </span>
                    </div>
                """
                
                # Then group by week within country
                for week_key, week_df in country_df.groupby('week_start', sort=True):
                    week_number = week_df['week_number'].iloc[0]
                    week_end = week_key + timedelta(days=6)
                    
                    html += f"""
                        <div class="week-summary">
                            <strong>Week {week_number} ({week_key.strftime('%b %d')} - {week_end.strftime('%b %d')})</strong>
                        </div>
                        <table>
                            <tr>
                                <th width="90">Date</th>
                                <th width="200">Customer</th>
                                <th width="180">Ship To</th>
                                <th width="100">DN Number</th>
                                <th width="80">PT Code</th>
                                <th width="120">Product</th>
                                <th width="80">Quantity</th>
                            </tr>
                    """
                    
                    # Group by delivery for display
                    display_df = week_df.groupby(['delivery_date', 'customer', 'recipient_company',
                                                'dn_number', 'product_id', 'pt_code', 'product_pn']).agg({
                        'remaining_quantity_to_deliver': 'sum'
                    }).reset_index()
                    
                    for _, row in display_df.iterrows():
                        html += f"""
                            <tr class="foreign-row">
                                <td>{row['delivery_date'].strftime('%b %d')}</td>
                                <td>{row['customer']}</td>
                                <td>{row['recipient_company']}</td>
                                <td>{row['dn_number']}</td>
                                <td>{row['pt_code']}</td>
                                <td>{row['product_pn']}</td>
                                <td>{row['remaining_quantity_to_deliver']:,.0f}</td>
                            </tr>
                        """
                    
                    html += "</table>"
        
        # Add customs information box
        html += """
            <div class="info-box">
                <h4>📋 Customs Documentation Requirements:</h4>
                <p><strong>For EPE (Xuất khẩu tại chỗ):</strong></p>
                <ul>
                    <li>Tờ khai xuất khẩu tại chỗ</li>
                    <li>C/O Form D nội địa</li>
                    <li>Hóa đơn VAT</li>
                    <li>Phiếu xuất kho</li>
                </ul>
                <p><strong>For Foreign Export:</strong></p>
                <ul>
                    <li>Export Declaration (Tờ khai xuất khẩu)</li>
                    <li>Certificate of Origin (based on destination country)</li>
                    <li>Commercial Invoice</li>
                    <li>Packing List</li>
                    <li>Bill of Lading / Airway Bill</li>
                </ul>
            </div>
            
            <div class="footer">
                <p>This is an automated customs clearance schedule from Outbound Logistics System</p>
                <p>For questions, please contact: <a href="mailto:outbound@prostech.vn">outbound@prostech.vn</a></p>
                <p>Phone: +84 33 476273</p>
            </div>
        </div>
        </body>
        </html>
        """
        
        return html

    def create_customs_excel_attachment(self, delivery_df):
        """Create Excel file for customs clearance with separate sheets"""
        output = io.BytesIO()
        
        # Create a copy for Excel export
        excel_df = delivery_df.copy()
        
        # Debug: Log available columns
        logger.info(f"Available columns in customs data: {excel_df.columns.tolist()}")
        
        # Format date columns
        date_columns = ['delivery_date', 'created_date', 'delivered_date', 'dispatched_date', 'sto_etd_date', 'oc_date', 'etd']
        for col in date_columns:
            if col in excel_df.columns:
                try:
                    excel_df[col] = pd.to_datetime(excel_df[col]).dt.strftime('%Y-%m-%d')
                except Exception as e:
                    logger.warning(f"Could not format date column {col}: {e}")
        
        # Remove duplicate columns
        excel_df = excel_df.loc[:, ~excel_df.columns.duplicated()]
        
        # Debug: Check etd column specifically
        logger.info(f"ETD column exists: {'etd' in excel_df.columns}")
        
        # Separate EPE and Foreign
        epe_df = excel_df[excel_df['customs_type'] == 'EPE'].copy()
        foreign_df = excel_df[excel_df['customs_type'] == 'Foreign'].copy()
        
        logger.info(f"EPE records: {len(epe_df)}, Foreign records: {len(foreign_df)}")
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            try:
                # Summary sheet
                summary_data = []
                
                # EPE summary by location
                if not epe_df.empty:
                    epe_summary = epe_df.groupby('recipient_state_province').agg({
                        'delivery_id': 'nunique',
                        'dn_number': 'nunique',
                        'remaining_quantity_to_deliver': 'sum',
                        'customer': 'nunique'
                    }).reset_index()
                    epe_summary['Type'] = 'EPE'
                    epe_summary.columns = ['Location', 'Deliveries', 'DN Count', 'Total Quantity', 'Customers', 'Type']
                    summary_data.append(epe_summary)
                
                # Foreign summary by country
                if not foreign_df.empty:
                    foreign_summary = foreign_df.groupby('customer_country_name').agg({
                        'delivery_id': 'nunique',
                        'dn_number': 'nunique',
                        'remaining_quantity_to_deliver': 'sum',
                        'customer': 'nunique'
                    }).reset_index()
                    foreign_summary['Type'] = 'Foreign'
                    foreign_summary.columns = ['Country', 'Deliveries', 'DN Count', 'Total Quantity', 'Customers', 'Type']
                    summary_data.append(foreign_summary)
                
                if summary_data:
                    summary_df = pd.concat(summary_data, ignore_index=True)
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # EPE Details sheet
                if not epe_df.empty:
                    logger.info("Creating EPE Details sheet...")
                    # Select important columns for EPE - check existence first
                    epe_columns_desired = [
                        'delivery_date', 'recipient_state_province', 'recipient_company',
                        'customer', 'dn_number', 'oc_number', 'pt_code', 'product_pn',
                        'remaining_quantity_to_deliver', 'etd', 'shipment_status_vn',
                        'preferred_warehouse', 'created_by_name'
                    ]
                    # Filter to only existing columns
                    epe_columns = [col for col in epe_columns_desired if col in epe_df.columns]
                    logger.info(f"EPE columns to export: {epe_columns}")
                    
                    # Check if critical columns exist
                    missing_cols = [col for col in epe_columns_desired if col not in epe_df.columns]
                    if missing_cols:
                        logger.warning(f"Missing EPE columns: {missing_cols}")
                    
                    if epe_columns:  # Only proceed if we have columns to export
                        epe_export = epe_df[epe_columns].copy()
                        
                        # Sort by available columns
                        sort_cols = ['recipient_state_province', 'delivery_date']
                        sort_cols = [col for col in sort_cols if col in epe_export.columns]
                        if sort_cols:
                            epe_export = epe_export.sort_values(sort_cols)
                        
                        epe_export.to_excel(writer, sheet_name='EPE Deliveries', index=False)
                        logger.info("EPE Details sheet created successfully")
                    else:
                        logger.warning("No columns available for EPE export")
                
                # Foreign Details sheet
                if not foreign_df.empty:
                    logger.info("Creating Foreign Details sheet...")
                    # Select important columns for Foreign - check existence first
                    foreign_columns_desired = [
                        'delivery_date', 'customer_country_name', 'customer',
                        'recipient_company', 'recipient_address', 'dn_number',
                        'oc_number', 'pt_code', 'product_pn', 'remaining_quantity_to_deliver',
                        'etd', 'shipment_status_vn', 'preferred_warehouse', 'created_by_name'
                    ]
                    # Filter to only existing columns
                    foreign_columns = [col for col in foreign_columns_desired if col in foreign_df.columns]
                    logger.info(f"Foreign columns to export: {foreign_columns}")
                    
                    # Check if critical columns exist
                    missing_cols = [col for col in foreign_columns_desired if col not in foreign_df.columns]
                    if missing_cols:
                        logger.warning(f"Missing Foreign columns: {missing_cols}")
                    
                    if foreign_columns:  # Only proceed if we have columns to export
                        foreign_export = foreign_df[foreign_columns].copy()
                        
                        # Sort by available columns
                        sort_cols = ['customer_country_name', 'delivery_date']
                        sort_cols = [col for col in sort_cols if col in foreign_export.columns]
                        if sort_cols:
                            foreign_export = foreign_export.sort_values(sort_cols)
                        
                        foreign_export.to_excel(writer, sheet_name='Foreign Deliveries', index=False)
                        logger.info("Foreign Details sheet created successfully")
                    else:
                        logger.warning("No columns available for Foreign export")
                
                # Timeline sheet - Weekly breakdown
                try:
                    # Process all deliveries
                    all_df = excel_df.copy()
                    
                    # Check if delivery_date exists and convert
                    if 'delivery_date' in all_df.columns:
                        all_df['delivery_date'] = pd.to_datetime(all_df['delivery_date'])
                        all_df['week_start'] = all_df['delivery_date'] - pd.to_timedelta(all_df['delivery_date'].dt.dayofweek, unit='D')
                        all_df['week_number'] = all_df['delivery_date'].dt.isocalendar().week
                        
                        # Group by week and type
                        weekly_summary = all_df.groupby(['week_start', 'week_number', 'customs_type']).agg({
                            'delivery_id': 'nunique',
                            'remaining_quantity_to_deliver': 'sum'
                        }).reset_index()
                        
                        weekly_summary.columns = ['Week Start', 'Week Number', 'Type', 'Deliveries', 'Quantity']
                        weekly_summary['Week End'] = weekly_summary['Week Start'] + timedelta(days=6)
                        
                        # Format dates
                        weekly_summary['Week Start'] = weekly_summary['Week Start'].dt.strftime('%Y-%m-%d')
                        weekly_summary['Week End'] = weekly_summary['Week End'].dt.strftime('%Y-%m-%d')
                        
                        weekly_summary = weekly_summary[['Week Number', 'Week Start', 'Week End', 'Type', 'Deliveries', 'Quantity']]
                        
                        weekly_summary.to_excel(writer, sheet_name='Weekly Timeline', index=False)
                    else:
                        logger.warning("delivery_date column not found for timeline sheet")
                except Exception as e:
                    logger.warning(f"Could not create timeline sheet: {e}")
                
                # Get workbook for formatting
                workbook = writer.book
                
                # Define formats
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#00796b',
                    'font_color': 'white',
                    'border': 1,
                    'text_wrap': True,
                    'valign': 'vcenter'
                })
                
                number_format = workbook.add_format({
                    'num_format': '#,##0',
                    'border': 1
                })
                
                # Apply formatting to all sheets
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    worksheet.set_column(0, 20, 15)  # Default width
                    worksheet.freeze_panes(1, 0)  # Freeze header row
                    
            except Exception as e:
                logger.error(f"Error creating customs Excel attachment: {e}")
                # Return basic Excel even if formatting fails
                try:
                    output.seek(0)
                    return output
                except:
                    raise
        
        output.seek(0)
        return output

    def send_customs_clearance_email(self, recipient_email, delivery_df, cc_emails=None, weeks_ahead=4):
        """Send customs clearance email to customs team"""
        try:
            # Check email configuration
            if not self.sender_email or not self.sender_password:
                logger.error("Email configuration missing. Please set EMAIL_SENDER and EMAIL_PASSWORD.")
                return False, "Email configuration missing. Please check environment variables."
            
            # Remove duplicate columns
            delivery_df = delivery_df.loc[:, ~delivery_df.columns.duplicated()]
            
            # Create message
            msg = MIMEMultipart('alternative')
            
            # Count deliveries
            epe_count = delivery_df[delivery_df['customs_type'] == 'EPE']['delivery_id'].nunique()
            foreign_count = delivery_df[delivery_df['customs_type'] == 'Foreign']['delivery_id'].nunique()
            
            week_text = f"{weeks_ahead} Week" if weeks_ahead == 1 else f"{weeks_ahead} Weeks"
            msg['Subject'] = f"🛃 Custom Clearance Schedule ({week_text}) - {epe_count} EPE & {foreign_count} Foreign Deliveries"
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            
            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)
            
            # Create HTML content
            html_content = self.create_customs_clearance_html(delivery_df, weeks_ahead)
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Create Excel attachment with fallback
            excel_attached = False
            try:
                excel_data = self.create_customs_excel_attachment(delivery_df)
                excel_part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                excel_part.set_payload(excel_data.read())
                encoders.encode_base64(excel_part)
                
                filename = f"customs_clearance_schedule_{datetime.now().strftime('%Y%m%d')}.xlsx"
                excel_part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(excel_part)
                excel_attached = True
                logger.info("Excel attachment created successfully")
            except Exception as e:
                logger.error(f"Error creating Excel attachment: {e}")
                # Try simplified CSV as fallback
                try:
                    csv_data = delivery_df.to_csv(index=False).encode('utf-8')
                    csv_part = MIMEBase('text', 'csv')
                    csv_part.set_payload(csv_data)
                    encoders.encode_base64(csv_part)
                    csv_part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="customs_clearance_schedule_{datetime.now().strftime("%Y%m%d")}.csv"'
                    )
                    msg.attach(csv_part)
                    logger.info("CSV fallback attachment created")
                except Exception as csv_error:
                    logger.error(f"Error creating CSV fallback: {csv_error}")
                    # Continue without attachment
            
            # Create ICS calendar attachment
            try:
                calendar_gen = CalendarEventGenerator()
                ics_content = calendar_gen.create_customs_ics_content(delivery_df, self.sender_email)
                
                if ics_content:
                    ics_part = MIMEBase('text', 'calendar')
                    ics_part.set_payload(ics_content.encode('utf-8'))
                    encoders.encode_base64(ics_part)
                    ics_part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="customs_clearance_{datetime.now().strftime("%Y%m%d")}.ics"'
                    )
                    msg.attach(ics_part)
            except Exception as e:
                logger.warning(f"Error creating calendar attachment: {e}")
                # Continue without calendar attachment
            
            # Send email
            logger.info(f"Attempting to send customs clearance email to {recipient_email}...")
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                
                recipients = [recipient_email]
                if cc_emails:
                    recipients.extend(cc_emails)
                
                server.sendmail(self.sender_email, recipients, msg.as_string())
            
            # Add note about attachment if failed
            attachment_note = ""
            if not excel_attached:
                attachment_note = " (Note: Excel attachment could not be created, please check logs)"
            
            logger.info(f"Customs clearance email sent successfully to {recipient_email}{attachment_note}")
            return True, f"Email sent successfully{attachment_note}"
            
        except smtplib.SMTPAuthenticationError:
            error_msg = "Email authentication failed. Please check your email credentials."
            logger.error(error_msg)
            return False, error_msg
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            logger.error(f"Error sending customs email: {e}", exc_info=True)
            return False, str(e)

    # ── ETD Update Notification ──────────────────────────────────

    def send_etd_update_notification(
        self,
        to_email,
        to_name,
        changes,
        updated_by_name,
        updated_by_email="",
        cc_emails=None,
        reason="",
    ):
        """Send ETD change notification email.

        Parameters
        ----------
        to_email : str
            Creator / primary recipient.
        to_name : str
            Friendly name for greeting.
        changes : list[dict]
            Each dict has: delivery_id, dn_number, customer,
            recipient_company, old_etd, new_etd.
        updated_by_name : str
            Who made the change.
        updated_by_email : str
            Email of the person who made the change (for CC).
        cc_emails : list[str]
            Additional CC addresses (e.g. dn_update@prostech.vn).
        reason : str
            Optional reason text.

        Returns
        -------
        (bool, str)
        """
        try:
            if not self.sender_email or not self.sender_password:
                return False, "Email configuration missing."

            # ── Build subject ────────────────────────────────────
            dn_count = len(changes)
            dn_list_short = ", ".join(
                str(c['dn_number']) for c in changes[:3]
            )
            if dn_count > 3:
                dn_list_short += f" (+{dn_count - 3} more)"

            subject = (
                f"📅 ETD Updated — {dn_count} Delivery"
                f"{'s' if dn_count > 1 else ''}: {dn_list_short}"
            )

            # ── Build HTML body ──────────────────────────────────
            html = self._build_etd_update_html(
                to_name, changes, updated_by_name,
                updated_by_email, reason,
            )

            # ── Compose MIME message ─────────────────────────────
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = to_email

            if cc_emails:
                msg['Cc'] = ', '.join(cc_emails)

            msg.attach(MIMEText(html, 'html'))

            # ── Send ─────────────────────────────────────────────
            recipients = [to_email]
            if cc_emails:
                recipients.extend(cc_emails)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipients, msg.as_string())

            logger.info(
                f"ETD update email sent to {to_email} "
                f"(CC: {cc_emails}) for {dn_count} DN(s)"
            )
            return True, "Email sent"

        except smtplib.SMTPAuthenticationError:
            error_msg = "Email auth failed — check credentials."
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            logger.error(f"ETD notification email error: {e}", exc_info=True)
            return False, str(e)

    def _build_etd_update_html(
        self, to_name, changes, updated_by_name,
        updated_by_email, reason,
    ):
        """Compose the ETD-change notification HTML."""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        dn_count = len(changes)

        # ── Table rows ───────────────────────────────────────────
        rows_html = ""
        for ch in changes:
            old_str = str(ch['old_etd']) if ch.get('old_etd') else '—'
            new_str = str(ch['new_etd']) if ch.get('new_etd') else '—'
            rows_html += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #e0e0e0;">{ch.get('dn_number','')}</td>
                <td style="padding:8px;border-bottom:1px solid #e0e0e0;">{ch.get('customer','')}</td>
                <td style="padding:8px;border-bottom:1px solid #e0e0e0;">{ch.get('recipient_company','')}</td>
                <td style="padding:8px;border-bottom:1px solid #e0e0e0;text-decoration:line-through;color:#999;">{old_str}</td>
                <td style="padding:8px;border-bottom:1px solid #e0e0e0;font-weight:bold;color:#1565c0;">{new_str}</td>
            </tr>"""

        reason_section = ""
        if reason:
            reason_section = f"""
            <div style="background:#fff3e0;border:1px solid #ffb74d;border-radius:5px;
                        padding:12px;margin:16px 0;">
                <strong>📝 Reason:</strong> {reason}
            </div>"""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; }}
            </style>
        </head>
        <body>
            <div style="background:#1565c0;color:white;padding:20px;text-align:center;">
                <h2 style="margin:0;">📅 ETD Update Notification</h2>
                <p style="margin:4px 0 0 0;opacity:0.9;">
                    {dn_count} delivery{'s' if dn_count > 1 else ''} updated
                </p>
            </div>

            <div style="padding:20px;">
                <p>Dear {to_name},</p>

                <p>
                    <strong>{updated_by_name}</strong>
                    {f'({updated_by_email})' if updated_by_email else ''}
                    has updated the Estimated Time of Delivery (ETD) for the
                    following delivery note{'s' if dn_count > 1 else ''}:
                </p>

                {reason_section}

                <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                    <thead>
                        <tr style="background:#f5f5f5;">
                            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">DN Number</th>
                            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">Customer</th>
                            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">Ship To</th>
                            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">Old ETD</th>
                            <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">New ETD</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>

                <div style="background:#e3f2fd;border:1px solid #90caf9;border-radius:5px;
                            padding:12px;margin:16px 0;">
                    <strong>ℹ️ Note:</strong> Please review the updated schedule and coordinate
                    with the warehouse / customer if necessary. If this change is incorrect,
                    please contact {updated_by_name} or reply to this email.
                </div>

                <p style="color:#999;font-size:12px;margin-top:24px;">
                    Updated at {now_str} · Outbound Logistics System · Prostech
                </p>
            </div>

            <div style="background:#f5f5f5;padding:16px;text-align:center;font-size:12px;color:#999;">
                This is an automated notification from the Delivery Schedule system.<br>
                For questions, contact:
                <a href="mailto:dn_update@prostech.vn">dn_update@prostech.vn</a>
            </div>
        </body>
        </html>
        """
        return html