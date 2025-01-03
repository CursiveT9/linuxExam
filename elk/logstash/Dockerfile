FROM docker.elastic.co/logstash/logstash:8.10.0

# Установить плагин OpenSearch
RUN logstash-plugin install logstash-output-opensearch

# Копирование конфигурации Logstash
COPY ./elk/logstash/logstash.conf /usr/share/logstash/pipeline/logstash.conf
