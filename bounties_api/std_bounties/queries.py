LEADERBOARD_QUERY = """
SELECT
	fulfillment.fulfiller as address,
	fulfillment_profiles.fulfiller_name as name,
	fulfillment_profiles.fulfiller_email as email,
	fulfillment_profiles."fulfiller_githubUsername" as githubUsername,
	bounty."tokenDecimals" as decimals,
	bounty."tokenSymbol" as symbol,
	SUM(bounty."fulfillmentAmount") as total,
	COUNT(bounty) as bounties_fulfilled,
	COUNT(fulfillment.id) as fulfillments_accepted
FROM std_bounties_fulfillment fulfillment
JOIN std_bounties_bounty bounty
ON fulfillment.bounty_id = bounty.id
JOIN
(
	SELECT
		fulfillments.fulfiller,
		fulfiller_name,
		fulfiller_email,
		"fulfiller_githubUsername"
	FROM std_bounties_fulfillment fulfillments
	INNER JOIN (
		SELECT
			fulfiller,
			MAX(created) as max_date
		FROM std_bounties_fulfillment
		GROUP BY fulfiller
	) max_date_fulfillment
	ON fulfillments.fulfiller = max_date_fulfillment.fulfiller
		AND fulfillments.created = max_date_fulfillment.max_date
) fulfillment_profiles
ON fulfillment.fulfiller = fulfillment_profiles.fulfiller
WHERE fulfillment.accepted = true
GROUP BY fulfillment.fulfiller, fulfillment_profiles.fulfiller_name, fulfillment_profiles.fulfiller_email, fulfillment_profiles."fulfiller_githubUsername", bounty."tokenDecimals", bounty."tokenSymbol"
ORDER BY total desc
"""