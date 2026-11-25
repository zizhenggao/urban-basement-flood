// The text of "About and limits". It describes what the page shows today: the map and the
// charts of finished 311 flooding requests. The Outreach agent is hidden, so it is not
// mentioned here. When the agent comes back, write its description again (the old one said
// "machine learning", which is wrong: the outreach score is plain arithmetic on ranks).
const LICENCE_URL = "https://www.toronto.ca/city-government/data-research-maps/open-data/open-data-licence/";
const DATASET_311_URL = "https://open.toronto.ca/dataset/311-service-requests-customer-initiated/";
const DATASET_WARDS_URL = "https://open.toronto.ca/dataset/city-wards/";
const EMAILS = ["afifytarnem@gmail.com", "zizheng.gaoprofessional@gmail.com", "mperezzevallos@gmail.com"];

const list = { margin: "0 0 14px", paddingLeft: 20, fontSize: 14 } as const;
const heading = { margin: "0 0 6px", fontSize: 16 } as const;
const paragraph = { margin: "0 0 14px", fontSize: 14 } as const;

export default function About({ onClose }: { onClose: () => void }) {
  return (
    <div className="drawer">
      <div className="dpanel" role="dialog" aria-label="About and limits">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <h2 className="h" style={{ fontSize: 22, flex: 1 }}>About and limits</h2>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        <p style={{ margin: "0 0 14px", padding: "12px 14px", borderRadius: 8, background: "#0B2545", color: "#fff", fontWeight: 600 }}>
          This map shows how many basement-flooding requests residents made to Toronto's 311 in each ward. It does not
          predict floods, and it never decides who is eligible for the subsidy.
        </p>

        <h3 style={heading}>How to read it</h3>
        <p style={paragraph}>
          Colour shows each ward's total of 311 flooding requests marked as done, from 2019 to October 2026. Red is the most
          requests and blue the fewest. Click a ward to see its requests by season and by year, stacked by request type.
          Each ward's charts use their own vertical axis, so read the numbers on the axis when comparing wards.
        </p>

        <h3 style={heading}>Data sources</h3>
        <ul style={list}>
          <li>
            City of Toronto Open Data:{" "}
            <a href={DATASET_311_URL} target="_blank" rel="noreferrer">311 Service Requests – Customer Initiated</a>, yearly
            files from 2019 to October 2026. Only requests the City marked as done are counted (their status was "Closed"
            until 2021 and "Completed" from 2022), for six request types: catch basin blocked or flooding, catch basin overflowing, maintenance hole overflowing,
            road water ponding, sewer main backup and sewer service line blocked.
          </li>
          <li>
            City of Toronto Open Data:{" "}
            <a href={DATASET_WARDS_URL} target="_blank" rel="noreferrer">City Wards</a>, 25-ward model (outlines simplified
            for display).
          </li>
          <li>
            Background reading: City of Toronto Basement Flooding Protection Program (BFPP) documents, used to understand
            the program. They are not used in the numbers shown on this map.
          </li>
          <li>
            Contains information licensed under the{" "}
            <a href={LICENCE_URL} target="_blank" rel="noreferrer">Open Government Licence – Toronto</a>.
          </li>
        </ul>

        <h3 style={heading}>Known limits</h3>
        <ul style={list}>
          <li>
            A request is a report, not a confirmed flood. After it is made, the City division that handles it may find it
            invalid or change its type.
          </li>
          <li>
            Not every flooding problem reaches 311. The data holds only the requests that 311 creates for some City
            divisions, leaves out requests created by City crews, and includes only requests with a location the City could
            validate. Wards where fewer people report can look safer than they are, so more requests does not mean more risk.
          </li>
          <li>
            Where people live changes the totals. Wards with more homes receive more requests, and the type of housing
            (houses or apartments) and the age of the sewers also play a part.
          </li>
          <li>
            Only requests marked as done are counted. Cancelled and still-open requests are left out, so the most recent months
            are undercounted. The data is published monthly, statuses keep changing, and this page uses files up to 31
            October 2026.
          </li>
          <li>A ward total can hide streets with very different conditions.</li>
        </ul>

        <h3 style={heading}>Send your feedback</h3>
        <p style={{ margin: 0, fontSize: 14 }}>
          Spot an error in a word, a figure or a policy detail? Write to the team at{" "}
          {EMAILS.map((email, i) => (
            <span key={email}>
              <a href={`mailto:${email}`}>{email}</a>
              {i < EMAILS.length - 2 ? ", " : i === EMAILS.length - 2 ? " or " : ""}
            </span>
          ))}
          .
        </p>
      </div>
    </div>
  );
}
