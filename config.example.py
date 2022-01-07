from dot import Config, DBConf, Env

config = Config()

# ca-certificate path:
config.ca_cert = '/path/to/ca-certificate.crt'

# K8S yaml configs:
config.k8s = {
    Env.STAGE: '/path/to/k8s-stage.yaml',
    Env.PROD: '/path/to/k8s-prod.yaml',
}

# Local postgres:
config.pg_conf = DBConf(
    host='localhost',
    name='postgres',
    password='postgres',
    user='postgres',
    port=5432,
)

# Remote postgres:
config.pull = {
    Env.STAGE: {
        'exchange': DBConf(
            host='db.host.stage',
            name='name',
            password='***********',
            user='user',
            port=5432,
        ),
    },
    Env.PROD: {
        'exchange': DBConf(
            host='db.host.prod',
            name='name',
            password='***********',
            user='user',
            port=5432,
        ),
    },
}
