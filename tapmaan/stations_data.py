"""Static metadata for the 50 monitoring stations used by Tapmaan.

Each record is an immutable tuple:
    (station_id, city, state, latitude, longitude, region_code, terrain)

region_code follows the seven temperature-homogeneous regions used by IMD:
    WH  Western Himalaya       NW  North West        NC  North Central
    NE  North East             WC  West Coast        EC  East Coast
    IP  Interior Peninsula
terrain decides which IMD heatwave criterion applies: "plains", "coastal" or "hilly".
The region assignment is approximate and meant for teaching.
"""

REGIONS = {
    "WH": "Western Himalaya",
    "NW": "North West",
    "NC": "North Central",
    "NE": "North East",
    "WC": "West Coast",
    "EC": "East Coast",
    "IP": "Interior Peninsula",
}

SEASONS = {
    "Winter": (1, 2),
    "Pre-monsoon": (3, 4, 5),
    "Monsoon": (6, 7, 8, 9),
    "Post-monsoon": (10, 11, 12),
}

STATIONS = (
    ("WS101", "Pune", "Maharashtra", 18.52, 73.86, "IP", "plains"),
    ("WS102", "Mumbai", "Maharashtra", 19.08, 72.84, "WC", "coastal"),
    ("WS103", "New Delhi", "Delhi", 28.58, 77.21, "NW", "plains"),
    ("WS104", "Kolkata", "West Bengal", 22.57, 88.36, "EC", "plains"),
    ("WS105", "Chennai", "Tamil Nadu", 13.08, 80.27, "EC", "coastal"),
    ("WS106", "Bengaluru", "Karnataka", 12.97, 77.59, "IP", "plains"),
    ("WS107", "Hyderabad", "Telangana", 17.39, 78.49, "IP", "plains"),
    ("WS108", "Ahmedabad", "Gujarat", 23.02, 72.57, "NW", "plains"),
    ("WS109", "Jaipur", "Rajasthan", 26.91, 75.79, "NW", "plains"),
    ("WS110", "Lucknow", "Uttar Pradesh", 26.85, 80.95, "NC", "plains"),
    ("WS111", "Kanpur", "Uttar Pradesh", 26.45, 80.33, "NC", "plains"),
    ("WS112", "Nagpur", "Maharashtra", 21.15, 79.09, "NC", "plains"),
    ("WS113", "Indore", "Madhya Pradesh", 22.72, 75.86, "NC", "plains"),
    ("WS114", "Bhopal", "Madhya Pradesh", 23.26, 77.41, "NC", "plains"),
    ("WS115", "Patna", "Bihar", 25.59, 85.14, "NC", "plains"),
    ("WS116", "Varanasi", "Uttar Pradesh", 25.32, 82.97, "NC", "plains"),
    ("WS117", "Prayagraj", "Uttar Pradesh", 25.44, 81.85, "NC", "plains"),
    ("WS118", "Agra", "Uttar Pradesh", 27.18, 78.01, "NW", "plains"),
    ("WS119", "Banda", "Uttar Pradesh", 25.48, 80.33, "NC", "plains"),
    ("WS120", "Jhansi", "Uttar Pradesh", 25.45, 78.57, "NC", "plains"),
    ("WS121", "Gwalior", "Madhya Pradesh", 26.22, 78.18, "NC", "plains"),
    ("WS122", "Kota", "Rajasthan", 25.21, 75.86, "NW", "plains"),
    ("WS123", "Jodhpur", "Rajasthan", 26.24, 73.02, "NW", "plains"),
    ("WS124", "Bikaner", "Rajasthan", 28.02, 73.31, "NW", "plains"),
    ("WS125", "Churu", "Rajasthan", 28.30, 74.95, "NW", "plains"),
    ("WS126", "Barmer", "Rajasthan", 25.75, 71.39, "NW", "plains"),
    ("WS127", "Chandigarh", "Chandigarh", 30.73, 76.78, "NW", "plains"),
    ("WS128", "Amritsar", "Punjab", 31.63, 74.87, "NW", "plains"),
    ("WS129", "Hisar", "Haryana", 29.15, 75.72, "NW", "plains"),
    ("WS130", "Dehradun", "Uttarakhand", 30.32, 78.03, "WH", "plains"),
    ("WS131", "Shimla", "Himachal Pradesh", 31.10, 77.17, "WH", "hilly"),
    ("WS132", "Srinagar", "Jammu and Kashmir", 34.08, 74.80, "WH", "hilly"),
    ("WS133", "Leh", "Ladakh", 34.15, 77.58, "WH", "hilly"),
    ("WS134", "Guwahati", "Assam", 26.14, 91.74, "NE", "plains"),
    ("WS135", "Shillong", "Meghalaya", 25.58, 91.89, "NE", "hilly"),
    ("WS136", "Agartala", "Tripura", 23.83, 91.28, "NE", "plains"),
    ("WS137", "Imphal", "Manipur", 24.82, 93.94, "NE", "plains"),
    ("WS138", "Bhubaneswar", "Odisha", 20.30, 85.82, "EC", "plains"),
    ("WS139", "Raipur", "Chhattisgarh", 21.25, 81.63, "NC", "plains"),
    ("WS140", "Ranchi", "Jharkhand", 23.34, 85.31, "NC", "plains"),
    ("WS141", "Visakhapatnam", "Andhra Pradesh", 17.69, 83.22, "EC", "coastal"),
    ("WS142", "Vijayawada", "Andhra Pradesh", 16.51, 80.65, "EC", "plains"),
    ("WS143", "Thiruvananthapuram", "Kerala", 8.52, 76.94, "WC", "coastal"),
    ("WS144", "Kochi", "Kerala", 9.93, 76.27, "WC", "coastal"),
    ("WS145", "Madurai", "Tamil Nadu", 9.93, 78.12, "IP", "plains"),
    ("WS146", "Coimbatore", "Tamil Nadu", 11.02, 76.96, "IP", "plains"),
    ("WS147", "Mangaluru", "Karnataka", 12.91, 74.86, "WC", "coastal"),
    ("WS148", "Panaji", "Goa", 15.50, 73.83, "WC", "coastal"),
    ("WS149", "Chandrapur", "Maharashtra", 19.96, 79.30, "NC", "plains"),
    ("WS150", "Solapur", "Maharashtra", 17.66, 75.91, "IP", "plains"),
)
