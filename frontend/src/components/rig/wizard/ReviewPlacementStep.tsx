import {
  Box, Typography, TextField, Table, TableBody,
  TableCell, TableHead, TableRow,
} from '@mui/material';

interface ReviewPlacementStepProps {
  rigName: string;
  onRigNameChange: (name: string) => void;
  stageWidth: number;
  stageDepth: number;
  stageHeight: number;
  placements: any[];
}

export default function ReviewPlacementStep({
  rigName, onRigNameChange, stageWidth, stageDepth, stageHeight, placements,
}: ReviewPlacementStepProps) {
  return (
    <Box>
      <Typography variant="h6" gutterBottom>Review & Create</Typography>

      <TextField
        label="Rig Name"
        value={rigName}
        onChange={(e) => onRigNameChange(e.target.value)}
        fullWidth
        sx={{ mb: 2 }}
      />

      <Typography variant="body2" color="text.secondary" gutterBottom>
        Stage: {stageWidth}m x {stageDepth}m x {stageHeight}m |{' '}
        {placements.length} fixtures
      </Typography>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>#</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Group</TableCell>
            <TableCell>Universe</TableCell>
            <TableCell>Address</TableCell>
            <TableCell>Position</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {placements.map((p, idx) => (
            <TableRow key={idx}>
              <TableCell>{idx + 1}</TableCell>
              <TableCell>{p.name}</TableCell>
              <TableCell>{p.group_name}</TableCell>
              <TableCell>{p.universe}</TableCell>
              <TableCell>{p.dmx_address}</TableCell>
              <TableCell>
                ({p.position_x?.toFixed(1)}, {p.position_y?.toFixed(1)}, {p.position_z?.toFixed(1)})
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
