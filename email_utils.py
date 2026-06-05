import os
import httpx

def send_reset_email(to_email: str, reset_link: str) -> None:
    """Send a password reset email using Brevo API directly via HTTP"""
    subject = "Réinitialisation de votre mot de passe - AgriTunisie"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Réinitialisation du mot de passe - AgriTunisie</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: #f4f7f6;
                margin: 0;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
            }}
            .header {{
                background: #ffffff;
                padding: 30px 30px 20px 30px;
                text-align: center;
                border-bottom: 2px solid #f0f4f2;
            }}
            .header h1 {{
                color: #1b5e20;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: -0.5px;
            }}
            .header h1 span {{ color: #2e7d32; font-weight: 400; }}
            .content {{ padding: 40px 35px; }}
            .greeting {{ font-size: 22px; font-weight: 600; color: #2d3748; margin-bottom: 20px; }}
            .message {{ font-size: 16px; line-height: 1.6; color: #4a5568; margin-bottom: 30px; }}
            .button-container {{ text-align: center; margin: 35px 0; }}
            .button {{
                display: inline-block;
                background-color: #10b981;
                color: #ffffff;
                text-decoration: none;
                padding: 14px 36px;
                border-radius: 12px;
                font-weight: 600;
                font-size: 16px;
                transition: background-color 0.3s ease;
                box-shadow: 0 4px 6px rgba(46, 125, 50, 0.2);
            }}
            .button:hover {{ 
                background-color: #059669;
                box-shadow: 0 6px 15px rgba(16, 185, 129, 0.35);
                transform: translateY(-1px); }}
            .info-box {{
                background: #f8fafc;
                border-left: 4px solid #2e7d32;
                padding: 18px;
                border-radius: 6px;
                margin: 30px 0;
                font-size: 15px;
                color: #4a5568;
            }}
            .info-box p {{ margin: 8px 0; }}
            .info-box p:first-child {{ margin-top: 0; }}
            .info-box p:last-child {{ margin-bottom: 0; }}
            .warning {{
                background: #fff5f5;
                border: 1px solid #fed7d7;
                padding: 16px;
                border-radius: 6px;
                margin-top: 30px;
                font-size: 14px;
                color: #c53030;
                text-align: center;
            }}
            .footer {{
                background: #f8fafc;
                padding: 24px 30px;
                text-align: center;
                border-top: 1px solid #e2e8f0;
            }}
            .footer p {{ color: #718096; font-size: 13px; margin: 6px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Agri<span>Tunisie</span></h1>
            </div>
            <div class="content">
                <div class="greeting">Bonjour,</div>
                <div class="message">
                    Nous avons reçu une demande de réinitialisation de votre mot de passe pour votre compte AgriTunisie. 
                    Cliquez sur le bouton ci-dessous pour créer un nouveau mot de passe sécurisé.
                </div>
                <div class="button-container">
                    <a href="{reset_link}" class="button">Réinitialiser mon mot de passe</a>
                </div>
                <div class="info-box">
                    <p><strong>📧 Compte :</strong> {to_email}</p>
                    <p><strong>⏰ Validité :</strong> Ce lien expire dans 15 minutes</p>
                </div>
                <div class="warning">
                    Vous n'avez pas demandé cette réinitialisation ? Vous pouvez ignorer cet email en toute sécurité.
                </div>
            </div>
            <div class="footer">
                <p>© 2026 AgriTunisie - Plateforme d'Agriculture Intelligente</p>
                <p>Cet email a été envoyé automatiquement, merci de ne pas y répondre.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_content = f"""Bonjour,

Nous avons reçu une demande de réinitialisation de votre mot de passe pour votre compte AgriTunisie.

Cliquez sur le lien suivant pour créer un nouveau mot de passe sécurisé (valable 15 minutes) :
{reset_link}

Compte concerné : {to_email}

⚠️ Vous n'avez pas demandé cette réinitialisation ? Ignorez cet email en toute sécurité.

---
© 2026 AgriTunisie - Plateforme d'Agriculture Intelligente
"""
    
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY environment variable not set")
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }
    payload = {
        "sender": {"name": "AgriTunisie Smart Farming", "email": "agritunisie.support@gmail.com"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
    }
    
    try:
        with httpx.Client() as client:
            response = client.post(url, headers=headers, json=payload, timeout=30.0)
            if response.status_code in (200, 201):
                print(f"✅ Email envoyé à {to_email} via Brevo")
            else:
                print(f"❌ Erreur Brevo: {response.status_code} - {response.text}")
                response.raise_for_status()
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi: {e}")
        raise