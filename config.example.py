from dot import Config, DBConf, Env

DIGITAL_OCEAN = 'postgresql-{0}-xxxxx-0.yyyyy.db.ondigitalocean.com'

config = Config(secret_dir='/absolute/path/to/your/.secrets')
config.ca_cert = 'ca-certificate.crt'
config.k8s = {Env.STAGE: 'k8s-stage.yaml', Env.PROD: 'k8s-prod.yaml'}

config.pg_conf = DBConf(
    host='localhost',
    name='postgres',
    password='postgres',
    user='postgres',
    port=5432,
)

config.pull = {
    Env.STAGE: {
        'exchange': DBConf(
            host=DIGITAL_OCEAN.format('common-stage'),
            name='rest_api',
            password='***********',
            user='rest_api',
            port=25060,
        ),
    },
    Env.PROD: {
        'exchange': DBConf(
            host=DIGITAL_OCEAN.format('common-prod'),
            name='rest_api_prod',
            password='***********',
            user='rest_api_prod',
            port=25060,
        ),
    },
}
