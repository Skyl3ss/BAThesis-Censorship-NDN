"""
Usage:
    sudo python3 scenario3.py your_topo.conf

Node roles (edit constants below to reassign):
    n0 = Root CA  (generates /root cert, signs producer cert)
    n1 = Producer (identity /root/site1, signs every data packet)
    n2 = Consumer (validates data against the certificate chain)
    All other nodes forward traffic as part of the NDN fabric.
"""

import os
import time
import re

from mininet.log import setLogLevel, info
from minindn.minindn import Minindn
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.apps.nlsr import Nlsr
from minindn.util import MiniNDNCLI

# ---------------------------------------------------------------------------
# Role constants — change these if you want different nodes
# ---------------------------------------------------------------------------
CA_NODE         = "n0"
PRODUCER_NODE   = "n1"
CONSUMER_NODE   = "n2"
MALICIOUS_NODE  = "n3"

PRODUCER_IDENTITY    = "/root/site1"
PRODUCER_PREFIX      = "/root/site1/data"
PRODUCER_CERT_PREFIX = "/root/site1/KEY"
PRODUCER_CERT_FILE   = "/tmp/n1/site1.ndncert"
PRODUCER_CONTENT     = "Hello, this data was signed by the verified producer!"

MALICIOUS_IDENTITY    = PRODUCER_IDENTITY
MALICIOUS_PREFIX      = PRODUCER_PREFIX
MALICIOUS_CERT_PREFIX = PRODUCER_CERT_PREFIX
MALICIOUS_CERT_FILE   = "/tmp/n3/site1.ndncert"
MALICIOUS_CONTENT     = "Hi, I'm a malicious producer and I want to trick you"

# ---------------------------------------------------------------------------
# Consumer validator config (written to disk before the consumer runs)
# ---------------------------------------------------------------------------
CONSUMER_VALIDATOR_CONF = """\
rule
{
    id "data-rule"
    for data
    filter
    {
        type name
        name /root
        relation is-prefix-of
    }
    checker
    {
        type hierarchical
        sig-type ecdsa-sha256
    }
}
trust-anchor
{
    type file
    file-name /tmp/n2/root.ndncert
}
"""

# ---------------------------------------------------------------------------
# Producer C++ — uses .format() so no nested quotes needed
# ---------------------------------------------------------------------------
PRODUCER_CPP_TEMPLATE = """\
#include <ndn-cxx/face.hpp>
#include <ndn-cxx/security/key-chain.hpp>
#include <ndn-cxx/security/signing-helpers.hpp>
#include <ndn-cxx/security/certificate.hpp>
#include <ndn-cxx/util/io.hpp>
#include <iostream>
#include <memory>
#include <string>

using namespace ndn;
using namespace std::placeholders;

static const std::string DATA_PREFIX      = "{prefix}";
static const std::string SIGNING_IDENTITY = "{signing_identity}";
static const std::string CERT_PREFIX      = "{cert_prefix}";
static const std::string CERT_FILE        = "{cert_file}";
static const std::string CONTENT          = "{content}";

class Producer {{
public:
    Producer()
    {{
        m_cert = io::load<security::Certificate>(CERT_FILE);
        if (!m_cert) {{
            throw std::runtime_error("Could not load producer certificate from " + CERT_FILE);
        }}

        std::cout << "[Producer] Loaded certificate: "
                  << m_cert->getName() << std::endl;
    }}

    void run() {{
        m_face.setInterestFilter(
            DATA_PREFIX,
            std::bind(&Producer::onDataInterest, this, _1, _2),
            std::bind(&Producer::onRegisterSuccess, this, _1),
            std::bind(&Producer::onRegisterFailed, this, _1, _2));
        std::cout << "[Producer] Listening on " << DATA_PREFIX << std::endl;

        m_face.setInterestFilter(
            CERT_PREFIX,
            std::bind(&Producer::onCertInterest, this, _1, _2),
            std::bind(&Producer::onRegisterSuccess, this, _1),
            std::bind(&Producer::onRegisterFailed, this, _1, _2));
        
        std::cout << "[Producer] Listening on data prefix " << DATA_PREFIX << std::endl;
        std::cout << "[Producer] Serving cert prefix " << CERT_PREFIX << std::endl;

        m_face.processEvents();
    }}

private:
    void onDataInterest(const InterestFilter&, const Interest& interest)
    {{
        std::cout << "[Producer] << Data Interest: " << interest.getName() << std::endl;

        auto data = std::make_shared<Data>(interest.getName());
        data->setFreshnessPeriod(time::seconds(10));
        data->setContent(std::string_view(CONTENT));

        m_keyChain.sign(*data, security::signingByIdentity(Name(SIGNING_IDENTITY)));

        std::cout << "[Producer] >> Signed data: " << data->getName() << std::endl;
        m_face.put(*data);
    }}

    void onCertInterest(const InterestFilter&, const Interest& interest)
    {{
        std::cout << "[Producer] << Cert Interest: " << interest.getName() << std::endl;

        const Name& certName = m_cert->getName();

        if (!interest.matchesData(*m_cert)) {{
            std::cerr << "[Producer] Certificate Interest does not match cert packet. "
                      << "Interest=" << interest.getName()
                      << " Cert=" << certName << std::endl;
            return;
        }}

        std::cout << "[Producer] >> Certificate: " << certName << std::endl;
        m_face.put(*m_cert);
    }}

    void onRegisterFailed(const Name& prefix, const std::string& reason) {{
        std::cerr << "[Producer] ERROR: failed to register prefix "
                  << prefix << ": " << reason << std::endl;
        m_face.shutdown();
    }}

    void onRegisterSuccess(const Name& prefix) {{
        std::cout << "[Producer] Successfully registered prefix " << prefix << std::endl;
    }}

    Face     m_face;
    KeyChain m_keyChain;
    std::shared_ptr<security::Certificate> m_cert;
}};

int main() {{
    try {{ Producer p; p.run(); }}
    catch (const std::exception& e) {{
        std::cerr << "[Producer] EXCEPTION: " << e.what() << std::endl;
        return 1;
    }}
    return 0;
}}
"""

# ---------------------------------------------------------------------------
# Consumer C++ — updated for ndn-cxx API that requires C++17:
#   - expressInterest now needs a NackCallback as 3rd arg
#   - validate success callback takes (const Data&) not shared_ptr
#   - Interest construction uses brace-init to avoid vexing parse
# ---------------------------------------------------------------------------
CONSUMER_CPP_TEMPLATE = """\
#include <ndn-cxx/face.hpp>
#include <ndn-cxx/security/validator-config.hpp>
#include <iostream>
#include <memory>
#include <string>

using namespace ndn;
using namespace std::placeholders;

static const std::string DEFAULT_PREFIX = "{prefix}";
static const std::string VALIDATOR      = "/tmp/n2/consumer-validator.conf";

class Consumer {{
public:
    explicit Consumer(std::string prefix)
      : m_prefix(std::move(prefix))
    {{
        m_face      = std::make_shared<Face>();
        m_validator = std::make_shared<security::ValidatorConfig>(*m_face);
        m_validator->load(VALIDATOR);
    }}

    void run() {{
        Interest interest{{Name(m_prefix)}};
        interest.setInterestLifetime(time::milliseconds(6000));
        interest.setMustBeFresh(true);

        std::cout << "[Consumer] >> Interest: " << interest.getName() << std::endl;

        m_face->expressInterest(
            interest,
            std::bind(&Consumer::onData,    this, _1, _2),
            std::bind(&Consumer::onNack,    this, _1, _2),
            std::bind(&Consumer::onTimeout, this, _1));

        m_face->processEvents();
    }}

private:
    void onData(const Interest&, const Data& data) {{
        std::cout << "[Consumer] << Data received, validating..." << std::endl;
        std::cout << "[Consumer] << Data name: " << data.getName() << std::endl;

        m_validator->validate(data,
            [this](const Data& d) {{
                std::string msg(
                    reinterpret_cast<const char*>(d.getContent().value()),
                    d.getContent().value_size());

                std::cout << "[Consumer] VALIDATION OK - content: "
                          << msg << std::endl;

                m_face->shutdown();
            }},
            [this](const Data&, const security::ValidationError& err) {{
                std::cerr << "[Consumer] VALIDATION FAILED: "
                          << err << std::endl;

                m_face->shutdown();
            }});
    }}

    void onNack(const Interest& interest, const lp::Nack& nack) {{
        std::cerr << "[Consumer] NACK for " << interest.getName()
                  << " reason: " << nack.getReason() << std::endl;

        m_face->shutdown();
    }}

    void onTimeout(const Interest& interest) {{
        std::cerr << "[Consumer] TIMEOUT for " << interest.getName() << std::endl;

        m_face->shutdown();
    }}

    std::string                                m_prefix;
    std::shared_ptr<Face>                      m_face;
    std::shared_ptr<security::ValidatorConfig> m_validator;
}};

int main(int argc, char** argv) {{
    try {{
        std::string prefix = DEFAULT_PREFIX;

        if (argc >= 2) {{
            prefix = argv[1];
        }}

        Consumer c(prefix);
        c.run();
    }}
    catch (const std::exception& e) {{
        std::cerr << "[Consumer] EXCEPTION: " << e.what() << std::endl;
        return 1;
    }}

    return 0;
}}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cmd(node, command, fatal=True):
    info("  [{}] $ {}\n".format(node.name, command))
    out = node.cmd(command + " ; echo __RC__$?")
    info(out)

    rc_marker = "__RC__"
    if rc_marker in out:
        rc = int(out.rsplit(rc_marker, 1)[1].strip().splitlines()[0])
        if fatal and rc != 0:
            raise RuntimeError("[{}] command failed rc={}: {}".format(
                node.name, rc, command))
    return out


def ndn_env(node):
    return "NDN_CLIENT_TRANSPORT=unix:///run/nfd/{}.sock ".format(node.name)


def compile_cpp(node, src_path, out_path):
    result = node.cmd(
        "g++ -std=c++17 {} -o {} "
        "$(pkg-config --cflags --libs libndn-cxx) -lpthread 2>&1".format(
            src_path, out_path)
    )
    if result.strip():
        info("  [{}] compiler: {}\n".format(node.name, result))
    return "error:" not in result.lower()

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def run_consumer_once(net, label):
    co = net.get(CONSUMER_NODE)

    info("\n*** Running consumer: {} ***\n".format(label))

    output = co.cmd(
        "export HOME=/tmp/minindn/n2; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n2.sock; "
        "/tmp/n2/consumer 2>&1"
    )

    info("\n--- Consumer output ({}) ---\n{}\n-----------------------\n".format(label, output))
    return output

def withdraw_malicious_prefixes(net):
    ma = net.get(MALICIOUS_NODE)
    co = net.get(CONSUMER_NODE)

    info("\n*** Withdrawing malicious advertisements from {} ***\n".format(MALICIOUS_NODE))

    run_cmd(ma, ndn_env(ma) + "nlsrc withdraw {}".format(MALICIOUS_PREFIX), fatal=False)
    run_cmd(ma, ndn_env(ma) + "nlsrc withdraw {}".format(MALICIOUS_CERT_PREFIX), fatal=False)

    time.sleep(5)

    info("\n--- n2 FIB after malicious withdrawal ---\n")
    info(co.cmd(
        "export HOME=/tmp/minindn/n2; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n2.sock; "
        "nfdc fib list | egrep '/root/site1/data|/root/site1/KEY' || true"
    ))

# ---------------------------------------------------------------------------
# Phase 1: Build certificate chain
# ---------------------------------------------------------------------------

def build_cert_chain(net):
    ca = net.get(CA_NODE)
    pr = net.get(PRODUCER_NODE)
    co = net.get(CONSUMER_NODE)

    info("\n*** [Phase 1] Building certificate chain ***\n")

    for node in [ca, pr, co]:
        node.cmd("mkdir -p /tmp/{}".format(node.name))

    # CA generates root cert
    info("  CA: generating /root certificate\n")
    run_cmd(ca, "ndnsec key-gen /root | tee /tmp/n0/root.ndncert | ndnsec cert-install -")

    # Copy root cert to consumer as trust anchor
    info("  Copying root cert -> consumer trust anchor\n")
    run_cmd(ca, "cp /tmp/n0/root.ndncert /tmp/n2/root.ndncert")

    # Producer generates keys and sends request to CA
    info("  Producer: generating keys for {}\n".format(PRODUCER_IDENTITY))
    run_cmd(pr, "ndnsec key-gen {} > /tmp/n1/site1.req".format(PRODUCER_IDENTITY))
    run_cmd(pr, "cp /tmp/n1/site1.req /tmp/n0/site1.req")

    # CA signs producer certificate
    info("  CA: signing producer certificate\n")
    run_cmd(ca, "ndnsec cert-gen -s /root /tmp/n0/site1.req > /tmp/n0/site1.ndncert")
    run_cmd(ca, "cp /tmp/n0/site1.ndncert /tmp/n1/site1.ndncert")

    # Both install it
    info("  Installing producer certificate on CA and Producer\n")
    run_cmd(pr, "ndnsec cert-install -f /tmp/n1/site1.ndncert")

    info("  Certificate chain built OK.\n")


def build_malicious_cert(net):
    ma = net.get(MALICIOUS_NODE)

    info("\n*** Building malicious certificate on {} ***\n".format(MALICIOUS_NODE))

    ma.cmd("mkdir -p /tmp/{}".format(MALICIOUS_NODE))

    info ("  Malicious producer: generating keys for {}\n".format(MALICIOUS_IDENTITY))

    run_cmd(ma, "ndnsec key-gen {} > {}".format(MALICIOUS_IDENTITY, MALICIOUS_CERT_FILE))
    run_cmd(ma, "ndnsec cert-install -f {}".format(MALICIOUS_CERT_FILE))

    info ("  Malicious certificate generated and installed on {}.\n".format(MALICIOUS_NODE))
    info (ma.cmd("ndnsec list -k 2>&1"))
    info (ma.cmd("ndnsec list -c 2>&1"))

    info ("  Malicious self-signed identity OK")



# ---------------------------------------------------------------------------
# Phase 2: Compile C++ apps
# ---------------------------------------------------------------------------

def compile_apps(net):
    pr = net.get(PRODUCER_NODE)
    ma = net.get(MALICIOUS_NODE)
    co = net.get(CONSUMER_NODE)

    info("\n*** [Phase 2] Compiling C++ applications ***\n")

    # Producer
    pr.cmd("mkdir -p /tmp/n1/src")
    producer_src = "/tmp/n1/src/producer.cpp"
    write_file(
        producer_src,
        PRODUCER_CPP_TEMPLATE.format(
            prefix=PRODUCER_PREFIX,
            signing_identity=PRODUCER_IDENTITY,
            cert_prefix=PRODUCER_CERT_PREFIX,
            cert_file=PRODUCER_CERT_FILE,
            content=PRODUCER_CONTENT
        )
    )
    ok = compile_cpp(pr, producer_src, "/tmp/n1/producer")
    info("  Producer compile: {}\n".format("OK" if ok else "FAILED"))    
    
    # Malicious Actor
    ma.cmd("mkdir -p /tmp/n3/src")
    producer_src = "/tmp/n3/src/producer.cpp"
    write_file(
        producer_src,
        PRODUCER_CPP_TEMPLATE.format(
            prefix=MALICIOUS_PREFIX,
            signing_identity=MALICIOUS_IDENTITY,
            cert_prefix=MALICIOUS_CERT_PREFIX,
            cert_file=MALICIOUS_CERT_FILE,
            content=MALICIOUS_CONTENT
        )
    )
    ok = compile_cpp(ma, producer_src, "/tmp/n3/producer")
    info("  Producer compile: {}\n".format("OK" if ok else "FAILED"))

    # Consumer
    co.cmd("mkdir -p /tmp/n2/src")
    write_file("/tmp/n2/consumer-validator.conf", CONSUMER_VALIDATOR_CONF)
    consumer_src = "/tmp/n2/src/consumer.cpp"
    write_file(consumer_src,
               CONSUMER_CPP_TEMPLATE.format(prefix=PRODUCER_PREFIX))
    ok = compile_cpp(co, consumer_src, "/tmp/n2/consumer")
    info("  Consumer compile: {}\n".format("OK" if ok else "FAILED"))


# ---------------------------------------------------------------------------
# Phase 3: Advertise prefixes and wait until FIB is actually populated
# ---------------------------------------------------------------------------

def wait_for_fib_entry(node, prefix, timeout=120):
    info("  Waiting for FIB entry '{}' on {}...\n".format(prefix, node.name))
    deadline = time.time() + timeout

    while time.time() < deadline:
        out = node.cmd(ndn_env(node) + "nfdc fib list 2>&1")
        if prefix in out:
            info("  FIB entry '{}' found on {}\n".format(prefix, node.name))
            return True
        time.sleep(2)

    info("  ERROR: FIB entry '{}' not found on {}\n".format(prefix, node.name))
    info(node.cmd(ndn_env(node) + "nfdc fib list 2>&1"))
    return False


def advertise_prefixes(net):
    pr = net.get(PRODUCER_NODE)
    ma = net.get(MALICIOUS_NODE)
    ca = net.get(CA_NODE)
    co = net.get(CONSUMER_NODE)

    info("\n*** [Phase 3] Advertising NDN prefixes ***\n")

    run_cmd(pr, ndn_env(pr) + "nlsrc advertise {}".format(PRODUCER_PREFIX))
    run_cmd(pr, ndn_env(pr) + "nlsrc advertise {}".format(PRODUCER_CERT_PREFIX))
    #run_cmd(ca, ndn_env(ca) + "nlsrc advertise /root/KEY")

    run_cmd(ma, ndn_env(ma) + "nlsrc advertise {}".format(MALICIOUS_PREFIX))
    run_cmd(ma, ndn_env(ma) + "nlsrc advertise {}".format(MALICIOUS_CERT_PREFIX))

    if not wait_for_fib_entry(co, PRODUCER_PREFIX, timeout=120):
        raise RuntimeError("Consumer has no FIB route to {}".format(PRODUCER_PREFIX))

    if not wait_for_fib_entry(co, PRODUCER_CERT_PREFIX, timeout=120):
        raise RuntimeError("Consumer has no FIB route to {}".format(PRODUCER_CERT_PREFIX))

    if not wait_for_fib_entry(co, MALICIOUS_PREFIX, timeout=120):
        raise RuntimeError("Consumer has no FIB route to {}".format(MALICIOUS_PREFIX))

    if not wait_for_fib_entry(co, MALICIOUS_CERT_PREFIX, timeout=120):
        raise RuntimeError("Consumer has no FIB route to {}".format(MALICIOUS_CERT_PREFIX))

    #if not wait_for_fib_entry(co, "/root/KEY", timeout=120):
    #    raise RuntimeError("Consumer has no FIB route to /root/KEY")


# ---------------------------------------------------------------------------
# Phase 4: Serve CA cert on-demand via ndnputchunks
# ---------------------------------------------------------------------------

def serve_ca_cert(net):
    ca = net.get(CA_NODE)

    info("\n*** [Phase 4] Serving CA certificate via ndnputchunks ***\n")
    ca.popen(
        "export HOME=/tmp/minindn/n0; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n0.sock; "
        "ndnputchunks /root/KEY < /tmp/n0/root.ndncert > /tmp/n0/putchunks.log 2>&1",
        shell=True)
    time.sleep(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_experiment():
    Minindn.cleanUp()
    setLogLevel("info")

    ndn = Minindn()
    ndn.start()

    info('Starting nfd and nlsr on nodes\n')
    AppManager(ndn, ndn.net.hosts, Nfd)
    AppManager(ndn, ndn.net.hosts, Nlsr)
    time.sleep(3)

    build_cert_chain(ndn.net)
    build_malicious_cert(ndn.net)
    compile_apps(ndn.net)

    
    advertise_prefixes(ndn.net)
    serve_ca_cert(ndn.net)

    # Start producer in background
    pr = ndn.net.get(PRODUCER_NODE)
    info("\n--- n1 security state immediately before producer launch ---\n")
    info(pr.cmd("echo HOME=$HOME"))
    info(pr.cmd("whoami"))
    info(pr.cmd("ndnsec list -k 2>&1"))
    info(pr.cmd("ndnsec list -c 2>&1"))
    info(pr.cmd("cat /tmp/minindn/n1/.ndn/client.conf 2>/dev/null || true"))
    info(pr.cmd("find /tmp/minindn/n1/.ndn -maxdepth 4 -type f -print 2>/dev/null || true"))

    info("\n--- n1 signing identity check ---\n")
    info(pr.cmd("ndnsec list -k 2>&1 | grep -A5 '/root/site1' || true"))
    pr.popen(
        "export HOME=/tmp/minindn/n1; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n1.sock; "
        "echo HOME=$HOME > /tmp/n1/producer-env.log; "
        "whoami >> /tmp/n1/producer-env.log; "
        "ndnsec list -k >> /tmp/n1/producer-env.log 2>&1; "
        "ndnsec list -c >> /tmp/n1/producer-env.log 2>&1; "
        "cat /tmp/minindn/n1/.ndn/client.conf >> /tmp/n1/producer-env.log 2>&1 || true; "
        "/tmp/n1/producer > /tmp/n1/producer.log 2>&1",
        shell=True
    )
    timeout = time.time() + 60
    while time.time() < timeout:
        log = pr.cmd("cat /tmp/n1/producer.log")
        if "Successfully registered prefix" in log:
            info("Producer is registered and ready.\n")
            break
        if "ERROR" in log:
            info("Producer failed to start. Check /tmp/n1/producer.log\n")
            return
        time.sleep(1)

    # Start malicious producer in background
    pr = ndn.net.get(MALICIOUS_NODE)
    info("\n--- n3 security state immediately before producer launch ---\n")
    info(pr.cmd("echo HOME=$HOME"))
    info(pr.cmd("whoami"))
    info(pr.cmd("ndnsec list -k 2>&1"))
    info(pr.cmd("ndnsec list -c 2>&1"))
    info(pr.cmd("cat /tmp/minindn/n3/.ndn/client.conf 2>/dev/null || true"))
    info(pr.cmd("find /tmp/minindn/n3/.ndn -maxdepth 4 -type f -print 2>/dev/null || true"))

    info("\n--- n3 signing identity check ---\n")
    info(pr.cmd("ndnsec list -k 2>&1 | grep -A5 '/root/site1' || true"))
    pr.popen(
        "export HOME=/tmp/minindn/n3; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n3.sock; "
        "echo HOME=$HOME > /tmp/n3/producer-env.log; "
        "whoami >> /tmp/n3/producer-env.log; "
        "ndnsec list -k >> /tmp/n3/producer-env.log 2>&1; "
        "ndnsec list -c >> /tmp/n3/producer-env.log 2>&1; "
        "cat /tmp/minindn/n3/.ndn/client.conf >> /tmp/n3/producer-env.log 2>&1 || true; "
        "/tmp/n3/producer > /tmp/n3/producer.log 2>&1",
        shell=True
    )
    timeout = time.time() + 60
    while time.time() < timeout:
        log = pr.cmd("cat /tmp/n3/producer.log")
        if "Successfully registered prefix" in log:
            info("Producer is registered and ready.\n")
            break
        if "ERROR" in log:
            info("Producer failed to start. Check /tmp/n3/producer.log\n")
            return
        time.sleep(1)


    # Run consumer twice:
    # 1. First run should hit malicious n3 and fail validation.
    # 2. Then withdraw n3's advertisements and run again.
    # 3. Second run should hit honest n1 and validate successfully.

    co = ndn.net.get(CONSUMER_NODE)

    info("\n--- n2 /root FIB before first consumer run ---\n")
    info(co.cmd(
        "export HOME=/tmp/minindn/n2; "
        "export NDN_CLIENT_TRANSPORT=unix:///run/nfd/n2.sock; "
        "nfdc fib list | grep /root || true"
    ))

    first = run_consumer_once(ndn.net, "malicious path expected")

    if "VALIDATION OK" in first:
        info("\n[WARNING] First fetch validated. Malicious path may not have won routing.\n")

    elif "VALIDATION FAILED" in first:
        info("\n[INFO] First fetch failed validation as expected. Now removing malicious route.\n")

        withdraw_malicious_prefixes(ndn.net)

        time.sleep(20)

        second = run_consumer_once(ndn.net, "honest path expected")

        if "VALIDATION OK" in second:
            info("\n[SUCCESS] Malicious Data rejected, honest Data accepted.\n")
        else:
            info("\n[FAILURE] Honest retry did not validate.\n")

    else:
        info("\n[FAILURE] First consumer run did not produce a validation result.\n")

    info("\n--- Honest producer log after consumer runs ---\n")
    info(ndn.net.get(PRODUCER_NODE).cmd("cat /tmp/n1/producer.log 2>&1"))

    info("\n--- Malicious producer log after consumer runs ---\n")
    info(ndn.net.get(MALICIOUS_NODE).cmd("cat /tmp/n3/producer.log 2>&1"))

    MiniNDNCLI(ndn.net)
    ndn.stop()


if __name__ == "__main__":
    run_experiment()


# sudo pkill -f /tmp/n1/consumer && sudo pkill -f /tmp/n1/producer && sudo pkill -f /tmp/n2/producer && sudo pkill -f /tmp/n2/consumer && sudo pkill -f /tmp/n3/producer && sudo pkill -f /tmp/n3/consumer 
# sudo rm -rf /tmp/minindn /tmp/n0 /tmp/n1/ /tmp/n2 /tmp/n3