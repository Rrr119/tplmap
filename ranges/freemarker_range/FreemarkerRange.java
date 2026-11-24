import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import freemarker.template.Configuration;
import freemarker.template.Template;

import java.io.StringReader;
import java.io.StringWriter;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Local FreeMarker SSTI range for tplmap detection benchmarks.
 *
 * <p>Contract (mirrors tests/env_java_tests/spark-app SparkApplication):
 *
 * <pre>
 * java -cp freemarker.jar FreemarkerRange.java --port 15013
 * GET /reflect/freemarker?tpl=&lt;template with %s&gt;&amp;inj=&lt;injection&gt;
 * </pre>
 *
 * <p>Paths containing {@code filter_canonical} enable a tiny denylist that
 * blocks the stock canonical comment probe ({@code <#-- ... -->}) while
 * arithmetic/string payload variants still evaluate.
 */
public class FreemarkerRange {

    private static Configuration cfg;

    public static void main(String[] args) throws Exception {
        int port = 15013;
        for (int i = 0; i < args.length - 1; i++) {
            if ("--port".equals(args[i])) {
                port = Integer.parseInt(args[i + 1]);
            }
        }

        cfg = new Configuration(Configuration.VERSION_2_3_34);
        cfg.setDefaultEncoding("UTF-8");
        cfg.setLogTemplateExceptions(false);
        cfg.setWrapUncheckedExceptions(true);

        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/", FreemarkerRange::handle);
        server.setExecutor(null);
        server.start();
        System.out.println("freemarker range listening on http://127.0.0.1:" + port);
    }

    private static void handle(HttpExchange exchange) {
        try {
            String path = exchange.getRequestURI().getPath();

            if (path.replaceAll("/+$", "").equals("/health")) {
                write(exchange, "ok");
                return;
            }

            Map<String, String> query = parseQuery(exchange.getRequestURI().getRawQuery());
            String tpl = query.getOrDefault("tpl", "%s");
            if (tpl == null || tpl.isEmpty()) {
                tpl = "%s";
            }
            String inj = query.getOrDefault("inj", "");
            if (inj == null) {
                inj = "";
            }

            String blockedToken = null;
            if (path.contains("filter_canonical") && inj.contains("<#--")) {
                // The stock FreeMarker test_render embeds a <#-- comment.
                blockedToken = "<#--";
            } else if (path.contains("filter_secondary") && inj.contains("<#")) {
                // Broader directive filter; ${...} variants still evaluate.
                blockedToken = "<#";
            }
            if (blockedToken != null) {
                write(exchange, "REQUEST BLOCKED BY RANGE FILTER");
                return;
            }

            String source = tpl.replace("%s", inj);
            String rendered = "";
            try {
                Template template = new Template("tpl", new StringReader(source), cfg);
                StringWriter writer = new StringWriter();
                template.process(null, writer);
                rendered = writer.toString();
            } catch (Exception e) {
                // Broken templates render nothing, like the upstream Spark range.
                rendered = "";
            }

            write(exchange, rendered);
        } catch (Exception fatal) {
            try {
                write(exchange, "");
            } catch (Exception ignored) {
                // connection already gone
            }
        }
    }

    private static Map<String, String> parseQuery(String rawQuery) {
        Map<String, String> values = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isEmpty()) {
            return values;
        }
        for (String pair : rawQuery.split("&")) {
            int eq = pair.indexOf('=');
            String key = eq >= 0 ? pair.substring(0, eq) : pair;
            String value = eq >= 0 ? pair.substring(eq + 1) : "";
            values.put(
                    URLDecoder.decode(key, StandardCharsets.UTF_8),
                    URLDecoder.decode(value, StandardCharsets.UTF_8));
        }
        return values;
    }

    private static void write(HttpExchange exchange, String body) throws Exception {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, data.length);
        exchange.getResponseBody().write(data);
        exchange.close();
    }
}
