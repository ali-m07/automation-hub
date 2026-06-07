"""
Email Service for sending bulk emails with images.
Moved from top-level email_service.py into automation_hub.services.
"""

import os
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional

import pandas as pd
import smtplib


class EmailService:
    """Handle email sending functionality."""

    def __init__(self) -> None:
        self.smtp_server = "smtp.example.com"
        self.smtp_port = 587

    def find_image_path(self, image_folder: str, image_name: str) -> Optional[str]:
        """Find image path in folder by name."""
        if not image_name:
            return None

        image_name = str(image_name).strip()
        folder_path = Path(image_folder)

        if not folder_path.exists():
            return None

        for ext in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
            potential_path = folder_path / f"{image_name}{ext}"
            if potential_path.exists():
                return str(potential_path)

        return None

    def send_bulk_emails(
        self,
        smtp_user: str,
        smtp_password: str,
        df: pd.DataFrame,
        subject: str,
        image_folder: Optional[str],
        attached_image_path: Optional[str],
        image_link: Optional[str],
        to_column: str,
        img_column: Optional[str],
        cc_columns: List[str],
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
    ) -> None:
        """Send bulk emails with images."""
        try:
            server_host = smtp_server or self.smtp_server
            server_port = smtp_port or self.smtp_port

            server = smtplib.SMTP(server_host, server_port)
            server.starttls()
            server.login(smtp_user, smtp_password)

            headers = df.columns.tolist()
            to_col_idx = headers.index(to_column) if to_column in headers else None
            img_col_idx = (
                headers.index(img_column)
                if img_column and img_column in headers
                else None
            )
            cc_col_indices = [headers.index(cc) for cc in cc_columns if cc in headers]

            success_count = 0
            error_count = 0

            for idx, row in df.iterrows():
                try:
                    email_address = row[to_col_idx] if to_col_idx is not None else None
                    if not email_address:
                        print(f"Row {idx + 2}: Missing email address. Skipping...")
                        error_count += 1
                        continue

                    cc_addresses = [
                        str(row[cc_idx])
                        for cc_idx in cc_col_indices
                        if cc_idx < len(row) and row[cc_idx]
                    ]

                    msg = MIMEMultipart("related")
                    msg["From"] = smtp_user
                    msg["To"] = str(email_address)
                    msg["Subject"] = subject
                    if cc_addresses:
                        msg["CC"] = ", ".join(cc_addresses)

                    image_path = None
                    if img_column and img_col_idx is not None:
                        image_name = (
                            row[img_col_idx] if img_col_idx < len(row) else None
                        )
                        if image_name and image_folder:
                            image_path = self.find_image_path(
                                image_folder, str(image_name)
                            )
                    elif attached_image_path:
                        image_path = attached_image_path

                    image_cid = "image_cid"
                    if image_link:
                        html_content = f"""
                        <html>
                            <body>
                                <div style="text-align: center;">
                                    <a href="{image_link}" target="_blank" rel="noopener noreferrer">
                                        <img src="cid:{image_cid}" style="width:768px; max-width:100%;">
                                    </a>
                                </div>
                            </body>
                        </html>
                        """
                    else:
                        html_content = f"""
                        <html>
                            <body>
                                <div style="text-align: center;">
                                    <img src="cid:{image_cid}" style="width:768px; max-width:100%;">
                                </div>
                            </body>
                        </html>
                        """

                    msg.attach(MIMEText(html_content, "html"))

                    if image_path and os.path.exists(image_path):
                        try:
                            with open(image_path, "rb") as img_file:
                                mime_image = MIMEImage(img_file.read())
                                mime_image.add_header("Content-ID", f"<{image_cid}>")
                                mime_image.add_header(
                                    "Content-Disposition",
                                    "inline",
                                    filename=os.path.basename(image_path),
                                )
                                msg.attach(mime_image)
                        except Exception as e:
                            print(f"Row {idx + 2}: Error attaching image: {str(e)}")

                    server.send_message(msg)
                    success_count += 1
                    print(f"Row {idx + 2}: Email sent successfully to {email_address}")
                except Exception as e:
                    error_count += 1
                    print(f"Row {idx + 2}: Failed to send email: {str(e)}")
                    continue

            server.quit()
            print(
                f"\nEmail sending completed: {success_count} successful, "
                f"{error_count} failed"
            )
        except smtplib.SMTPAuthenticationError as e:
            print(f"SMTP Authentication Error: {str(e)}")
            raise
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error sending emails: {str(e)}")
            raise

    def send_notification_email(
        self,
        smtp_user: str,
        smtp_password: str,
        to_email: str,
        subject: str,
        html_body: str,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
    ) -> None:
        """Send a single HTML notification email."""
        try:
            server_host = smtp_server or self.smtp_server
            server_port = smtp_port or self.smtp_port

            server = smtplib.SMTP(server_host, server_port)
            server.starttls()
            server.login(smtp_user, smtp_password)

            msg = MIMEMultipart("alternative")
            msg["From"] = smtp_user
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(html_body, "html"))

            server.send_message(msg)
            server.quit()
            print(f"Notification email sent to {to_email}")
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error sending notification email: {str(e)}")
            raise
