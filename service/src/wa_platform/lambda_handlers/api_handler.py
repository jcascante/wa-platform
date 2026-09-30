from mangum import Mangum

from wa_platform.api.app import app

handler = Mangum(app)
