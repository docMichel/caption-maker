# /usr/local/etc/httpd/extra/httpd-caption-maker.conf
# Proxy pour l'API Flask Caption Maker

Listen *:5001

# Configuration globale du proxy
ProxyIOBufferSize 65536
ProxyTimeout 300

<VirtualHost *:5001>
    ServerName caption-api.local
    DocumentRoot "/usr/local/var/www/caption-api"
    
    # Logs
    ErrorLog "/var/log/apache2/caption-api-error.log"
    CustomLog "/var/log/apache2/caption-api-access.log" common
    
    # Modules nécessaires
    <IfModule mod_headers.c>
        <IfModule mod_rewrite.c>
            # Supprimer les headers CORS venant de Flask
            Header unset Access-Control-Allow-Origin
            Header unset Access-Control-Allow-Methods
            Header unset Access-Control-Allow-Headers
        
            # Headers CORS pour TOUTES les réponses
            Header always set Access-Control-Allow-Origin "*"
            Header always set Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
            Header always set Access-Control-Allow-Headers "Content-Type, Authorization, X-Requested-With"
            Header always set Access-Control-Allow-Credentials "true"
            
            # Gestion des requêtes OPTIONS (preflight CORS)
            RewriteEngine On
            RewriteCond %{REQUEST_METHOD} OPTIONS
            RewriteRule ^(.*)$ - [R=204,L]
            
        </IfModule>
    </IfModule>
    
    # Configuration du proxy vers Flask
    ProxyRequests Off
    ProxyPreserveHost On
    ProxyPass / http://localhost:5000/
    ProxyPassReverse / http://localhost:5000/
    
    # Configuration spéciale pour les endpoints SSE (Server-Sent Events)
    <Location ~ "/api/ai/generate-caption-stream">
        Header set Cache-Control "no-cache"
        Header set X-Accel-Buffering "no"
        SetEnv no-gzip 1
        SetEnv proxy-nokeepalive 1
    </Location>
    
    # Permissions
    <Directory "/usr/local/var/www/caption-api">
        Require all granted
    </Directory>
    
</VirtualHost>