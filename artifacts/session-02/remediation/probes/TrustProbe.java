import java.nio.file.*;
import java.security.cert.*;
import java.util.*;
import javax.net.ssl.*;

public class TrustProbe {
    public static void main(String[] args) throws Exception {
        TrustManagerFactory factory = TrustManagerFactory.getInstance("PKIX");
        factory.init((java.security.KeyStore) null);
        X509TrustManager trust = Arrays.stream(factory.getTrustManagers())
            .filter(x -> x instanceof X509TrustManager).map(x -> (X509TrustManager) x)
            .findFirst().orElseThrow();
        // Positive control: the validator must still accept an ordinary trusted anchor.
        X509Certificate anchor = trust.getAcceptedIssuers()[0];
        trust.checkServerTrusted(new X509Certificate[]{anchor}, anchor.getPublicKey().getAlgorithm());
        System.out.println("positive_trusted_anchor=PASS");
        int total = 0, accepted = 0;
        CertificateFactory certs = CertificateFactory.getInstance("X.509");
        try (var paths = Files.list(Path.of(args[0]))) {
            for (Path path : paths.filter(x -> x.toString().endsWith(".pem")).sorted().toList()) {
                X509Certificate[] chain;
                try (var input = Files.newInputStream(path)) {
                    chain = certs.generateCertificates(input).toArray(X509Certificate[]::new);
                }
                total++;
                try {
                    trust.checkServerTrusted(chain, chain[0].getPublicKey().getAlgorithm());
                    accepted++;
                    System.out.println("ACCEPTED " + path.getFileName());
                } catch (CertificateException expected) {
                    System.out.println("REJECTED " + path.getFileName() + " " + expected.getClass().getSimpleName());
                }
            }
        }
        System.out.println("total=" + total + " accepted=" + accepted);
        if (total != 14 || accepted != 0) throw new AssertionError("Compromised chains accepted or incomplete corpus");
    }
}
